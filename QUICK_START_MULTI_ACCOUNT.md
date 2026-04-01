# Quick Start Guide: Multi-Account Mode

## 🚀 Enable Multi-Account Support

### Step 1: Create accounts.json

```bash
mkdir -p ~/.config/kiro-gateway
cat > ~/.config/kiro-gateway/accounts.json << 'EOF'
{
  "accounts": [
    {
      "email": "account1@example.com",
      "tokens": {
        "access": "your_access_token_1",
        "refresh": "your_refresh_token_1",
        "expires_at": 1735689600000
      },
      "enabled": true,
      "is_invalid": false,
      "model_rate_limits": {},
      "last_used": null,
      "health_score": 1.0,
      "metadata": {"region": "us-east-1"}
    },
    {
      "email": "account2@example.com",
      "tokens": {
        "access": "your_access_token_2",
        "refresh": "your_refresh_token_2",
        "expires_at": 1735689600000
      },
      "enabled": true,
      "is_invalid": false,
      "model_rate_limits": {},
      "last_used": null,
      "health_score": 1.0,
      "metadata": {"region": "us-east-1"}
    }
  ],
  "settings": {
    "strategy": "hybrid",
    "active_index": 0
  }
}
EOF
```

### Step 2: Update .env

Add to your `.env` file:

```env
# Enable multi-account mode
MULTI_ACCOUNT_ENABLED=true

# Path to accounts file
ACCOUNTS_FILE="~/.config/kiro-gateway/accounts.json"

# Selection strategy (sticky, round-robin, or hybrid)
ACCOUNT_STRATEGY="hybrid"
```

### Step 3: Start the server

```bash
python main.py
```

You should see:

```
2026-03-31 11:45:43 | INFO | Multi-account mode enabled
2026-03-31 11:45:43 | INFO | AccountManager initialized: 2/2 accounts available (strategy: hybrid)
```

---

## 🧪 Test Multi-Account Failover

### Test 1: Basic Request

```bash
curl -X POST http://localhost:9000/v1/chat/completions \
  -H "Authorization: Bearer your-proxy-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'
```

### Test 2: Trigger Rate Limit (Simulate)

To test failover, you can manually edit `accounts.json` while the server is running:

```json
{
  "accounts": [
    {
      "email": "account1@example.com",
      "model_rate_limits": {
        "claude-sonnet-4-5": {
          "is_rate_limited": true,
          "reset_time": 1735689600000,
          "consecutive_failures": 1
        }
      }
    }
  ]
}
```

Then make another request - it should automatically use account2.

### Test 3: Check Account Status

```bash
# View logs to see which account was used
tail -f logs/kiro-gateway.log | grep "AccountManager\|Strategy"
```

---

## 📊 Monitor Account Health

### Check accounts.json

```bash
cat ~/.config/kiro-gateway/accounts.json | jq '.accounts[] | {email, health_score, last_used, rate_limits: .model_rate_limits}'
```

### Expected Output

```json
{
  "email": "account1@example.com",
  "health_score": 1.0,
  "last_used": 1735603200000,
  "rate_limits": {}
}
{
  "email": "account2@example.com",
  "health_score": 0.95,
  "last_used": 1735603300000,
  "rate_limits": {
    "claude-sonnet-4-5": {
      "is_rate_limited": false,
      "reset_time": null,
      "consecutive_failures": 0
    }
  }
}
```

---

## 🔄 Switch Strategies

### Change strategy at runtime

Edit `accounts.json`:

```json
{
  "settings": {
    "strategy": "round-robin",
    "active_index": 0
  }
}
```

Then reload (requires server restart or reload endpoint).

---

## 🐛 Troubleshooting

### Issue: "No available accounts"

**Cause**: All accounts are rate-limited or invalid.

**Solution**:
1. Check `accounts.json` for rate limits
2. Wait for rate limits to expire
3. Add more accounts

### Issue: "AccountManager not initialized"

**Cause**: `MULTI_ACCOUNT_ENABLED=false` or accounts.json not found.

**Solution**:
1. Set `MULTI_ACCOUNT_ENABLED=true` in `.env`
2. Create `accounts.json` at the specified path
3. Restart server

### Issue: Accounts not rotating

**Cause**: Using sticky strategy with healthy accounts.

**Solution**:
- Switch to `round-robin` strategy for maximum rotation
- Or trigger rate limits to see failover in action

---

## 📈 Performance Tips

### For Maximum Throughput
```env
ACCOUNT_STRATEGY="round-robin"
MAX_ACCOUNT_RETRIES=3
```

### For Cache Optimization
```env
ACCOUNT_STRATEGY="sticky"
RATE_LIMIT_MAX_WAIT_MS=120000
```

### For Balanced Performance
```env
ACCOUNT_STRATEGY="hybrid"
MAX_ACCOUNT_RETRIES=5
```

---

## 🔐 Security Best Practices

1. **Protect accounts.json**
   ```bash
   chmod 600 ~/.config/kiro-gateway/accounts.json
   ```

2. **Use environment-specific files**
   ```bash
   # Development
   ACCOUNTS_FILE="./accounts.dev.json"
   
   # Production
   ACCOUNTS_FILE="/etc/kiro-gateway/accounts.json"
   ```

3. **Rotate tokens regularly**
   - Update tokens in accounts.json
   - Server will use new tokens on next request

4. **Monitor for invalid accounts**
   ```bash
   cat accounts.json | jq '.accounts[] | select(.is_invalid == true)'
   ```

---

## ✅ Verification Checklist

- [ ] `accounts.json` created with valid tokens
- [ ] `MULTI_ACCOUNT_ENABLED=true` in `.env`
- [ ] Server starts without errors
- [ ] Log shows "AccountManager initialized"
- [ ] Requests succeed with account rotation
- [ ] Rate limits trigger failover
- [ ] State persists across restarts

---

## 🎯 Next Steps

1. **Add more accounts** to increase throughput
2. **Monitor health scores** to identify problematic accounts
3. **Tune strategy** based on your workload
4. **Set up alerts** for when all accounts are rate-limited

---

## 📚 Additional Resources

- **Architecture**: See `CLAUDE.md` for detailed architecture
- **Implementation**: See `IMPLEMENTATION_COMPLETE.md` for technical details
- **Testing**: See `tests/unit/test_account_manager.py` for examples
