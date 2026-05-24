# Singaporean Chinese Dictionary

Search local Chinese terms by Hanyu Pinyin, Chinese characters, or English.

## Project Structure

```bash
sg-chinese/
├── index.html          - Main page
├── style.css
├── app.js              - Frontend JS (search, sort, theme, SW)
├── sw.js               - PWA service worker
├── manifest.json       - PWA manifest
├── vercel.json         - Vercel routing + headers config
├── package.json        - Node deps (Supabase client for API)
└── api/
    └── search.js       - Serverless search endpoint
```
