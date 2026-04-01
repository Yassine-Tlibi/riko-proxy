# -*- coding: utf-8 -*-

"""
Kiro Portal OAuth - Web-based Google/GitHub authentication.

Opens https://app.kiro.dev/signin in the browser and captures the OAuth callback.
This provides the same Google/GitHub login experience as Kiro IDE.
"""

import asyncio
import secrets
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any
from loguru import logger


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles OAuth callback from Kiro portal."""

    callback_data: Optional[Dict[str, Any]] = None

    def send_cors_headers(self):
        """Send CORS headers for AJAX requests."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def do_OPTIONS(self):
        """Handle preflight CORS requests."""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def _process_params(self, params: dict):
        """Extract and store tokens from parameters."""
        OAuthCallbackHandler.callback_data = {
            'access_token': params.get('access_token', [None])[0] if 'access_token' in params else None,
            'refresh_token': params.get('refresh_token', [None])[0] if 'refresh_token' in params else None,
            'profile_arn': params.get('profile_arn', [None])[0] if 'profile_arn' in params else None,
            'expires_at': params.get('expires_at', [None])[0] if 'expires_at' in params else None,
            'provider': params.get('provider', ['Unknown'])[0] if 'provider' in params else 'Unknown',
        }
        logger.info(f"OAuth callback data extracted: provider={OAuthCallbackHandler.callback_data.get('provider')}")

    def do_POST(self):
        """Handle POST request with JSON or form payload from OAuth portal frontend."""
        parsed = urlparse(self.path)
        if parsed.path in ['/oauth/callback', '/signin/callback']:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length).decode('utf-8')
                
                # Check if JSON
                if self.headers.get('Content-Type', '').startswith('application/json'):
                    try:
                        import json
                        data = json.loads(post_data)
                        # Convert dict to format expected by _process_params (lists of strings)
                        params = {k: [str(v)] for k, v in data.items()}
                        self._process_params(params)
                    except Exception as e:
                        logger.error(f"Failed to parse JSON POST data in OAuth callback: {e}")
                else:
                    # Parse as form URL-encoded
                    params = parse_qs(post_data)
                    self._process_params(params)

            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            
            logger.info("OAuth POST callback processed successfully")
        else:
            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()

    def do_GET(self):
        """Handle GET request from OAuth callback."""
        parsed = urlparse(self.path)

        if parsed.path in ['/oauth/callback', '/signin/callback']:
            params = parse_qs(parsed.query)

            # Extract tokens if available in query params
            if 'access_token' in params or 'refresh_token' in params:
                self._process_params(params)

            # Send success response page (for browser redirects)
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            success_html = """
            <html>
            <head><title>Authentication Successful</title></head>
            <body style="font-family: system-ui; padding: 40px; text-align: center; background: #0F172A; color: #F8FAFC;">
                <h1 style="color: #22C55E;">✅ Authentication Successful!</h1>
                <p>You can close this window and return to Kiro Gateway.</p>
                <script>
                    if (window.location.hash && window.location.hash.includes('access_token')) {
                        // Extract query string format from hash without the #
                        const hashParams = window.location.hash.substring(1);
                        fetch('/oauth/callback', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                            body: hashParams
                        }).then(() => {
                            setTimeout(() => window.close(), 2000);
                        }).catch(e => console.error(e));
                    } else {
                        setTimeout(() => window.close(), 2000);
                    }
                </script>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode())

            if OAuthCallbackHandler.callback_data:
                logger.info(f"OAuth callback received via GET: provider={OAuthCallbackHandler.callback_data.get('provider')}")
        else:
            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


async def start_oauth_flow(port: int = 51121) -> Optional[Dict[str, Any]]:
    """
    Start OAuth flow by opening Kiro portal and waiting for callback.

    Args:
        port: Port for local callback server (default: 51121)

    Returns:
        Dict with tokens if successful, None otherwise
    """
    state = secrets.token_urlsafe(32)

    # Build Kiro portal URL
    portal_url = f"https://app.kiro.dev/signin?redirect_uri=http://127.0.0.1:{port}/oauth/callback&state={state}"

    logger.info(f"Starting OAuth flow on port {port}")
    logger.info(f"Opening browser: {portal_url}")

    # Reset callback data
    OAuthCallbackHandler.callback_data = None

    # Start local server
    server = HTTPServer(('127.0.0.1', port), OAuthCallbackHandler)

    # Open browser
    webbrowser.open(portal_url)

    # Wait for callback (timeout after 5 minutes) - FIXED: Use asyncio.to_thread for blocking operations
    timeout = 300
    start_time = asyncio.get_event_loop().time()

    try:
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            # Run blocking server.handle_request() in thread pool to avoid blocking event loop
            await asyncio.to_thread(server.handle_request)

            if OAuthCallbackHandler.callback_data:
                logger.info("OAuth callback received successfully")
                return OAuthCallbackHandler.callback_data

            # Small delay to prevent busy waiting
            await asyncio.sleep(0.1)

    except Exception as e:
        logger.error(f"OAuth flow error: {e}")
        return None
    finally:
        # Ensure server is properly closed
        try:
            server.server_close()
        except Exception as e:
            logger.warning(f"Error closing OAuth server: {e}")

    logger.error("OAuth flow timed out")
    return None
