# Using the API Documentation (Swagger UI)

## Accessing the Docs

Visit: `https://mise.elidibus.com/docs` (or `http://localhost:8000/docs` for local development)

## Authenticating in Swagger UI

Since all endpoints (except `/api/health`) require API key authentication, you need to provide your API key to test the API from Swagger UI.

### Step-by-Step:

1. **Open the docs page**
   ```
   https://mise.elidibus.com/docs
   ```

2. **Click the "Authorize" button**
   - Located in the top-right corner
   - Has a lock icon 🔓

3. **Enter your API key**
   - Field name: `X-API-Key`
   - Value: Your API key (e.g., `abc123...`)
   - The same key you use in `API_KEYS` environment variable

4. **Click "Authorize"**
   - The lock icon will change to 🔒

5. **Click "Close"**

6. **Test endpoints**
   - Now all requests will include your API key
   - Try the "Try it out" button on any endpoint
   - Click "Execute" to make the request

## Example: Testing the Health Endpoint

1. Find `GET /api/health` in the docs
2. Click "Try it out"
3. Click "Execute"
4. See the response:
   ```json
   {
     "status": "ok",
     "database": "connected"
   }
   ```

## Example: Creating an Ingestion Request

1. **Authorize first** (see steps above)
2. Find `POST /api/ingestions`
3. Click "Try it out"
4. Edit the request body:
   ```json
   {
     "source_type": "text",
     "text": "Chocolate Chip Cookies\n\nIngredients:\n- 2 cups flour\n- 1 cup butter\n\nInstructions:\n1. Mix ingredients\n2. Bake at 350°F for 10 minutes"
   }
   ```
5. Click "Execute"
6. See the response with your new ingestion request

## Alternative: Using curl

If you prefer command-line:

```bash
# Get API key from your .env file
export API_KEY="your-api-key-here"

# Test health endpoint (no auth needed)
curl https://mise.elidibus.com/api/health

# List recipes (requires auth)
curl -H "X-API-Key: $API_KEY" https://mise.elidibus.com/api/recipes

# Create ingestion request
curl -X POST https://mise.elidibus.com/api/ingestions \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "text",
    "text": "Recipe text here..."
  }'
```

## Development Mode (No Authentication)

When testing locally without setting `API_KEYS` environment variable:

```bash
# Start API without API_KEYS set
uv run mise-api

# Visit http://localhost:8000/docs
# No authentication required!
# All endpoints work without the Authorize step
```

This is **only for local development** - never deploy to production without `API_KEYS` set!

## Troubleshooting

### "Missing API key" Error

**Problem:** Getting 401 Unauthorized when testing endpoints

**Solution:**
1. Make sure you clicked "Authorize" and entered your API key
2. Verify the key matches what's in your `.env` file (`API_KEYS=...`)
3. Check that the lock icon is 🔒 (locked)

### "Invalid API key" Error

**Problem:** Getting 403 Forbidden

**Solution:**
1. Double-check your API key is correct
2. Ensure no extra spaces or newlines in the key
3. Verify the server has the correct `API_KEYS` environment variable
4. Restart the API server if you just changed `API_KEYS`

### Can't Access /docs Page

**Problem:** Browser shows connection error

**Solution:**
1. Ensure the API server is running: `docker-compose ps`
2. Check nginx is routing correctly: `sudo nginx -t && sudo systemctl status nginx`
3. Verify DNS: `nslookup mise.elidibus.com`
4. Check SSL certificate: `sudo certbot certificates`

## Security Note

**Never share your API key!**
- The API key gives full access to your recipe database
- Each family member should have their own key (comma-separated in `API_KEYS`)
- Rotate keys regularly: `openssl rand -hex 32`

## ReDoc Alternative

FastAPI also provides ReDoc documentation:

```
https://mise.elidibus.com/redoc
```

ReDoc is read-only (no "Try it out" feature) but has a cleaner layout for browsing the API structure.
