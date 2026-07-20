# Security Deployment Checklist

Use this checklist before deploying to production.

## 🔐 Environment Configuration

- [ ] Copy `.env.example` to `.env` in backend directory
- [ ] Set `ENVIRONMENT=production` in `.env`
- [ ] Generate strong `GEMINI_API_KEY` from https://ai.google.dev
- [ ] Set `ALLOWED_ORIGINS` to your actual domain (e.g., `https://myapp.com`)
- [ ] Set `ALLOWED_HOSTS` to your actual domain
- [ ] Remove default values from `.env`
- [ ] Store `.env` in secure location (NOT in version control)
- [ ] Use a secrets management system (AWS Secrets Manager, Vault, etc.)

## 🐳 Docker & Container Security

- [ ] Verify Dockerfile uses `python:3.11-alpine` (minimal base image)
- [ ] Verify non-root user is created (`appuser:1000`)
- [ ] Verify health check is configured
- [ ] Run container with `--read-only` where possible
- [ ] Set resource limits in docker-compose.yml
- [ ] Scan Docker image for vulnerabilities: `trivy image job-trailerd-backend`
- [ ] Use specific versions in base image (no `:latest`)
- [ ] Remove unnecessary packages from image

## 🔒 Application Security

- [ ] Run security scan: `safety check`
- [ ] Run code analysis: `bandit -r backend/`
- [ ] Verify all endpoints have rate limiting
- [ ] Check CORS configuration for your domain only
- [ ] Verify security headers are enabled
- [ ] Check no debug information in error responses
- [ ] Verify logging is configured and working
- [ ] Check database uses parameterized queries
- [ ] Verify no hardcoded secrets in code

## 🌐 Network Security

- [ ] Use HTTPS/TLS in production (not HTTP)
- [ ] Configure reverse proxy (nginx, Caddy)
- [ ] Enable HSTS (HTTP Strict Transport Security)
- [ ] Configure firewall rules
- [ ] Use Web Application Firewall (WAF) if available
- [ ] Whitelist specific IP addresses if possible
- [ ] Disable CORS if not needed
- [ ] Use HTTPS for all external API calls

## 💾 Data Security

- [ ] Enable database encryption at rest
- [ ] Set up automated database backups
- [ ] Test database restore procedures
- [ ] Implement access control for database
- [ ] Use strong database passwords
- [ ] Never commit `.env` files to git
- [ ] Add `.env` to `.gitignore`
- [ ] Implement data retention policies
- [ ] Enable audit logging for sensitive operations

## 🔑 API Security

- [ ] Verify API keys are rotated regularly
- [ ] Use environment variables for secrets (never hardcode)
- [ ] Implement API authentication
- [ ] Add request signing if needed
- [ ] Verify API rate limiting is appropriate
- [ ] Monitor API usage for anomalies
- [ ] Implement request/response logging (sensitive data masked)
- [ ] Set up API documentation without exposing internals

## 🛡️ Dependency Management

- [ ] Run `pip install --upgrade -r requirements.txt` to get latest versions
- [ ] Check for deprecated dependencies
- [ ] Review all dependencies for security advisories
- [ ] Subscribe to security mailing lists for key dependencies
- [ ] Pin specific versions (not `>=`)
- [ ] Regularly audit dependencies: `safety check`
- [ ] Document why each dependency is needed
- [ ] Remove unused dependencies

## 👤 Access Control

- [ ] Implement authentication (if needed for your use case)
- [ ] Create separate admin and user roles
- [ ] Implement authorization checks
- [ ] Use strong password policies
- [ ] Enable multi-factor authentication where possible
- [ ] Limit SSH/admin access to specific IPs
- [ ] Implement principle of least privilege
- [ ] Document who has access to what

## 📊 Monitoring & Logging

- [ ] Enable application logging (INFO level minimum)
- [ ] Set up log aggregation (ELK, Splunk, CloudWatch)
- [ ] Monitor error rates and anomalies
- [ ] Set up alerts for security events
- [ ] Review logs regularly for suspicious activity
- [ ] Implement request ID tracking for debugging
- [ ] Mask sensitive data in logs
- [ ] Set up log retention policies
- [ ] Monitor resource usage (CPU, memory, disk)

## 🧪 Testing & Validation

- [ ] Run unit tests: `pytest tests/`
- [ ] Run integration tests
- [ ] Perform security testing: `bandit`, `safety check`
- [ ] Run SAST (Static Application Security Testing)
- [ ] Test rate limiting effectiveness
- [ ] Test CORS configuration
- [ ] Verify all error responses are generic
- [ ] Test with invalid/malicious inputs
- [ ] Performance test under load
- [ ] Disaster recovery testing

## 🚀 Deployment Process

- [ ] Use CI/CD pipeline with automated security checks
- [ ] Review all code changes before deployment
- [ ] Maintain deployment documentation
- [ ] Use blue-green or canary deployments
- [ ] Implement rollback procedures
- [ ] Test rollback procedures
- [ ] Have a deployment checklist
- [ ] Require multiple approvals for production deployments
- [ ] Document all deployment changes
- [ ] Maintain a change log

## 🔄 Maintenance & Updates

- [ ] Schedule regular security audits
- [ ] Update dependencies monthly
- [ ] Monitor security advisories
- [ ] Update Docker base images regularly
- [ ] Review and update security policies quarterly
- [ ] Conduct security training for team
- [ ] Review access logs monthly
- [ ] Test backup restoration procedures
- [ ] Update incident response procedures

## 🆘 Incident Response

- [ ] Have an incident response plan documented
- [ ] Define security contacts and escalation procedures
- [ ] Have a process for security vulnerability reports
- [ ] Maintain security incident logs
- [ ] Have a post-incident review process
- [ ] Document lessons learned
- [ ] Update procedures based on incidents
- [ ] Have a communication plan for security breaches

## 📋 Compliance & Legal

- [ ] Ensure compliance with applicable regulations (GDPR, HIPAA, etc.)
- [ ] Have privacy policy documented
- [ ] Have terms of service reviewed by legal
- [ ] Implement data retention policies
- [ ] Have a data breach response procedure
- [ ] Document security measures
- [ ] Have a vulnerability disclosure policy
- [ ] Review third-party data sharing agreements

## ✅ Pre-Deployment Sign-Off

**Before deploying to production:**

1. **Security Lead**: 
   - [ ] Reviewed all security configurations
   - [ ] Signature: _________________ Date: _______

2. **DevOps/Infrastructure**:
   - [ ] Verified infrastructure security
   - [ ] Signature: _________________ Date: _______

3. **Project Lead**:
   - [ ] Approved for production deployment
   - [ ] Signature: _________________ Date: _______

---

## 🔍 Quick Security Audit Command

Run this before deployment:

```bash
#!/bin/bash

echo "🔍 Running Security Audit..."
echo ""

echo "1. Checking Python dependencies..."
pip install safety
safety check

echo ""
echo "2. Running Bandit (code analysis)..."
pip install bandit
bandit -r backend/ -ll

echo ""
echo "3. Checking for hardcoded secrets..."
pip install detect-secrets
detect-secrets scan backend/

echo ""
echo "4. Checking Docker image..."
docker build -t job-trailerd:latest ./backend
echo "For full Docker scan, run: trivy image job-trailerd:latest"

echo ""
echo "5. Checking environment variables..."
if [ ! -f backend/.env ]; then
    echo "❌ ERROR: backend/.env not found!"
    echo "   Copy backend/.env.example to backend/.env and fill in values"
    exit 1
fi

echo ""
echo "✅ Security audit complete!"
```

---

**Last Updated**: 2026-06-17  
**Checklist Version**: 1.0
