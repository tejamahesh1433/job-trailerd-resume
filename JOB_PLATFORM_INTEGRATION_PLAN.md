# Job Platform Integration Plan

## Project Overview
Your **Job Tailored Resume** system is a FastAPI + React app that:
- Takes job descriptions
- Analyzes & tailors resumes to match
- Generates cover letters & mail drafts
- Integrates with Gmail

---

## Integration Goal
Add **job aggregation** from 5 platforms:
- LinkedIn
- Dice
- ZipRecruiter
- Indeed
- JobSeeker

---

## Architecture Options

### **Option 1: Real-time API Search (Lightweight)**
```
User enters search params (role, location, salary)
→ Frontend calls your backend
→ Backend queries job platform APIs
→ Results displayed, user picks one
→ Your system tailors resume
```
**Pros**: No data storage, always fresh
**Cons**: Slow (API calls), rate limits, users wait

---

### **Option 2: Scheduled Sync (Recommended)**
```
Cron job (hourly/daily)
→ Fetches jobs from all platforms
→ Stores in SQLite `jobs` table
→ User searches locally (fast)
→ Auto-sync latest jobs
```
**Pros**: Fast search, offline access, better UX
**Cons**: Needs storage, data can be stale (1-24hrs)

---

### **Option 3: Hybrid (Best UX)**
```
Popular/trending jobs cached locally
+ Niche/filtered searches fetch live APIs
+ Fallback to aggregator APIs
```
**Pros**: Best balance
**Cons**: Most complex

---

## Platform APIs & Auth

### 1. **LinkedIn Jobs**
- **API**: LinkedIn Jobs API (business account required)
- **Auth**: OAuth 2.0
- **Rate Limit**: 100 reqs/day (free tier)
- **Cost**: Expensive for volume
- **Best For**: Premium corporate integrations

### 2. **Indeed**
- **API**: Indeed Publisher API
- **Auth**: API Key
- **Rate Limit**: 300 reqs/hour (free)
- **Cost**: Free tier available
- **Best For**: Bulk job scraping
- **Doc**: https://opensource.indeedeng.io/api-documentation/

### 3. **ZipRecruiter**
- **API**: ZipRecruiter API (partner required)
- **Auth**: API Key
- **Rate Limit**: Varies by plan
- **Cost**: Contact sales
- **Best For**: Enterprise partnerships

### 4. **Dice** (Tech jobs)
- **API**: Dice Career API
- **Auth**: API Key
- **Rate Limit**: Rate limited
- **Cost**: Free tier + paid plans
- **Doc**: https://dice.com/api

### 5. **JobSeeker / Generic**
- **API**: Some have REST APIs, many need scraping
- **Auth**: Varies
- **Cost**: Free to expensive

### **Better Option: Use Aggregator APIs**
Instead of integrating each individually, use:
- **RapidAPI Job Search APIs** (easy, aggregated)
- **JSearch API** (RapidAPI marketplace)
- **Adzuna API** (job aggregator)

---

## Recommended Approach

### **Tech Stack**
```
Frontend: React (add search/filter UI)
Backend: FastAPI + new `jobs` service
Database: SQLite (add `jobs` table)
Scheduler: APScheduler (Python, runs in background)
API Client: requests library
Caching: Simple file cache or Redis (optional)
```

### **Database Schema**

```sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    platform TEXT,              -- 'linkedin', 'indeed', 'dice', etc
    platform_id TEXT UNIQUE,    -- Job ID from source platform
    title TEXT,
    company TEXT,
    location TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    currency TEXT,
    description TEXT,
    url TEXT,
    posted_date DATETIME,
    expires_date DATETIME,
    job_type TEXT,              -- 'full-time', 'contract', etc
    remote BOOLEAN,
    keywords TEXT,              -- JSON array of extracted skills
    raw_json TEXT,              -- Store full API response
    created_at DATETIME,
    fetched_at DATETIME
);

CREATE TABLE job_searches (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,            -- Later: multi-user support
    search_query TEXT,
    location TEXT,
    saved_at DATETIME,
    results_count INTEGER
);

CREATE TABLE job_bookmarks (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    job_id INTEGER,
    bookmarked_at DATETIME,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
```

---

## Implementation Steps

### **Phase 1: Foundation (Week 1)**
1. Add `jobs` table to SQLite
2. Create `services/job_fetcher.py` with base classes
3. Implement one API (Indeed or JSearch)
4. Test data flow

### **Phase 2: Multi-Platform (Week 2)**
1. Add 2-3 more platforms
2. Add scheduler to sync daily
3. Build search/filter endpoints

### **Phase 3: Frontend UI (Week 3)**
1. Add job search page to React
2. Display results with filters
3. "Apply with tailored resume" button
4. Link job → scan process

### **Phase 4: Polish (Week 4)**
1. Add bookmarks/saved jobs
2. Search history
3. Advanced filters (salary range, remote, etc)

---

## Code Examples

### **Backend: Job Fetcher Service**

```python
# backend/services/job_fetcher.py
import requests
from abc import ABC, abstractmethod
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class JobFetcher(ABC):
    """Base class for job platform APIs"""
    
    @abstractmethod
    def search(self, query: str, location: str = "", **kwargs) -> list:
        """Fetch jobs and return standardized format"""
        pass
    
    def _normalize_job(self, raw_job: dict, platform: str) -> dict:
        """Convert platform-specific format to standard format"""
        return {
            'platform': platform,
            'platform_id': raw_job.get('id'),
            'title': raw_job.get('title'),
            'company': raw_job.get('company'),
            'location': raw_job.get('location', ''),
            'description': raw_job.get('description'),
            'url': raw_job.get('url'),
            'posted_date': raw_job.get('posted_date'),
            'salary_min': raw_job.get('salary_min'),
            'salary_max': raw_job.get('salary_max'),
            'job_type': raw_job.get('job_type', 'full-time'),
            'remote': raw_job.get('remote', False),
        }


class IndeedJobFetcher(JobFetcher):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.indeed.com/ads/api"
    
    def search(self, query: str, location: str = "", **kwargs) -> list:
        params = {
            'publisher': self.api_key,
            'q': query,
            'l': location,
            'format': 'json',
            'limit': kwargs.get('limit', 25)
        }
        try:
            resp = requests.get(f"{self.base_url}/jobs", params=params, timeout=10)
            resp.raise_for_status()
            results = resp.json().get('results', [])
            return [self._normalize_job(job, 'indeed') for job in results]
        except Exception as e:
            logger.error(f"Indeed API error: {e}")
            return []


class JSearchFetcher(JobFetcher):
    """JSearch API from RapidAPI (aggregates many sources)"""
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://jsearch.p.rapidapi.com/search"
        self.headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
        }
    
    def search(self, query: str, location: str = "", **kwargs) -> list:
        params = {
            'query': f"{query} {location}",
            'page': kwargs.get('page', 1),
            'num_pages': 1
        }
        try:
            resp = requests.get(self.base_url, headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            results = resp.json().get('data', [])
            return [self._normalize_job(job, 'jsearch') for job in results]
        except Exception as e:
            logger.error(f"JSearch API error: {e}")
            return []


# Backend: Scheduler for daily sync
# backend/services/job_scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from services.job_fetcher import IndeedJobFetcher, JSearchFetcher
from database import save_jobs
import os

def schedule_job_sync():
    """Start background scheduler to fetch jobs daily"""
    scheduler = BackgroundScheduler()
    
    def fetch_and_save():
        logger.info("Starting job fetch...")
        
        # Fetch from multiple platforms
        fetchers = [
            IndeedJobFetcher(os.getenv("INDEED_API_KEY")),
            JSearchFetcher(os.getenv("JSEARCH_API_KEY")),
        ]
        
        all_jobs = []
        for fetcher in fetchers:
            jobs = fetcher.search("DevOps Engineer", location="USA")
            all_jobs.extend(jobs)
        
        # Deduplicate and save
        save_jobs(all_jobs)
        logger.info(f"Saved {len(all_jobs)} jobs")
    
    # Run every day at 2 AM
    scheduler.add_job(fetch_and_save, 'cron', hour=2, minute=0)
    scheduler.start()
```

### **Backend: New API Endpoints**

```python
# In main.py or routes/jobs.py

@app.get("/api/jobs/search")
async def search_jobs(query: str, location: str = "", platforms: str = "all"):
    """Search jobs across platforms"""
    try:
        from services.job_fetcher import IndeedJobFetcher, JSearchFetcher
        
        fetchers = []
        if platforms in ['all', 'indeed']:
            fetchers.append(IndeedJobFetcher(os.getenv("INDEED_API_KEY")))
        if platforms in ['all', 'jsearch']:
            fetchers.append(JSearchFetcher(os.getenv("JSEARCH_API_KEY")))
        
        all_jobs = []
        for fetcher in fetchers:
            jobs = fetcher.search(query, location)
            all_jobs.extend(jobs)
        
        return {"jobs": all_jobs, "total": len(all_jobs)}
    except Exception as e:
        logger.error(f"Job search error: {e}")
        raise HTTPException(status_code=500, detail="Job search failed")


@app.post("/api/jobs/apply")
async def apply_with_tailored_resume(job_id: str, platform: str):
    """
    Get a specific job and trigger resume tailoring workflow
    Similar to /api/scan but starts with a saved job
    """
    try:
        # Fetch job from database or API
        job = get_job(job_id, platform)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Use existing scan endpoint with job description
        # Reuse your tailoring logic!
        
        return {
            "message": "Resume tailored",
            "job": job,
            "tailored_resume": "..."
        }
    except Exception as e:
        logger.error(f"Apply error: {e}")
        raise HTTPException(status_code=500, detail="Failed to apply")


@app.get("/api/jobs/bookmarks")
async def get_bookmarked_jobs():
    """Return user's saved jobs"""
    jobs = get_bookmarked_jobs()
    return {"jobs": jobs}


@app.post("/api/jobs/{job_id}/bookmark")
async def bookmark_job(job_id: str):
    """Save a job for later"""
    save_bookmark(job_id)
    return {"status": "bookmarked"}
```

### **Frontend: Job Search Component**

```jsx
// frontend/src/pages/JobSearch.jsx
import React, { useState } from 'react';

export default function JobSearch() {
  const [query, setQuery] = useState('');
  const [location, setLocation] = useState('');
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const res = await fetch(`/api/jobs/search?query=${query}&location=${location}`);
      const data = await res.json();
      setJobs(data.jobs);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async (jobId, platform) => {
    // Trigger resume tailoring for this job
    const res = await fetch(`/api/jobs/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, platform })
    });
    
    const result = await res.json();
    alert('Resume tailored! Check your history.');
  };

  return (
    <div style={{ padding: '20px' }}>
      <h1>Find & Apply Jobs</h1>
      
      <form onSubmit={handleSearch}>
        <input
          type="text"
          placeholder="Role (e.g., DevOps Engineer)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <input
          type="text"
          placeholder="Location (e.g., New York)"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
        <button type="submit">{loading ? 'Searching...' : 'Search'}</button>
      </form>

      <div className="jobs-list">
        {jobs.map((job) => (
          <div key={job.platform_id} className="job-card">
            <h3>{job.title}</h3>
            <p>{job.company} • {job.location}</p>
            {job.salary_min && (
              <p>${job.salary_min} - ${job.salary_max}</p>
            )}
            <p>{job.description.substring(0, 200)}...</p>
            <a href={job.url} target="_blank">View on {job.platform}</a>
            <button onClick={() => handleApply(job.platform_id, job.platform)}>
              Tailor Resume & Apply
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## Environment Variables

```bash
# .env
INDEED_API_KEY=your_indeed_api_key
JSEARCH_API_KEY=your_jsearch_api_key
LINKEDIN_CLIENT_ID=your_linkedin_id
LINKEDIN_CLIENT_SECRET=your_linkedin_secret
DICE_API_KEY=your_dice_api_key
ZIPRECRUITER_API_KEY=your_ziprecruiter_api_key

# Scheduler settings
JOB_SYNC_INTERVAL_HOURS=24
JOB_SYNC_ENABLED=true
```

---

## Cost Breakdown

| Platform | Free Tier | Cost |
|----------|-----------|------|
| Indeed | 300 reqs/hr | Free |
| JSearch (RapidAPI) | 100 reqs/month | $5-50/month |
| LinkedIn | Limited | $500+/month |
| Dice | Limited | Contact sales |
| ZipRecruiter | Limited | Contact sales |

**Cheapest Option**: Indeed + JSearch (~$5-10/month)

---

## Quick Start Checklist

- [ ] Create `jobs` table in SQLite
- [ ] Choose API (recommend Indeed + JSearch)
- [ ] Get API keys
- [ ] Create `services/job_fetcher.py`
- [ ] Add job search endpoints
- [ ] Add React search page
- [ ] Test end-to-end workflow
- [ ] Deploy with scheduler

---

## Alternative: Use Existing Scraping Library

If APIs are too expensive/limited, use:
```python
# pip install beautifulsoup4 selenium requests-html
from selenium import webdriver

# Scrape Indeed, LinkedIn, etc
# (Follow robots.txt, rate limiting rules)
```

**Not Recommended**: Fragile, slow, may violate ToS

---

## Next Steps

1. **Choose integration method**: Real-time vs Scheduled vs Hybrid
2. **Pick 2-3 platforms** to start (suggest Indeed + JSearch)
3. **Get API keys** and test one platform
4. **Database schema** - extend your SQLite
5. **Scheduler** - add APScheduler for daily sync
6. **Frontend UI** - add search page
7. **Link workflow** - job search → tailored resume

Would you like me to help with any specific step?
