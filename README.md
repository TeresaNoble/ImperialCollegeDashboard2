# Imperial College Dashboard

## Environment Setup

This application requires a Dimensions API key to fetch publication data. The key must be provided as an environment variable:

### Local Development
```bash
export DIMENSIONS_API_KEY="your_key_here"
python server_edited.py
```

### GitHub Actions
The Dimensions API key must be configured as a repository secret named `DIMENSIONS_API_KEY`:

1. Go to repository Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `DIMENSIONS_API_KEY`
4. Value: Your Dimensions API key
5. Click "Add secret"

The workflow will automatically use this secret when running tests and deployments.