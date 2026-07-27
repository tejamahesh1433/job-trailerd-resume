import React, { useState, useEffect, useRef } from 'react';
import './index.css';
import JobMatcher from './JobMatcher';
import SearchPage from './SearchPage';
import CommandCenter from './CommandCenter';
import JobMatches from './JobMatches';
import InboxPage from './InboxPage';

const TECH_EXPERIENCE = [
  // Cloud Platforms
  { name: 'AWS (general)', category: 'Cloud Platforms', years: '10+ years', rating: '9.5/10', info: { use: 'It\'s the cloud platform basically everything runs on — compute, storage, databases, networking, all of it.', how: 'You spin up whatever you need on demand and pay for what you use, either through the console, the CLI, or Terraform.', where: 'I\'ve used AWS as the primary cloud at every shop I\'ve been at — Mizuho, State of Tennessee, Omnicell, and Freddie Mac.' } },
  { name: 'EC2', category: 'Cloud Platforms', years: '10+ years', rating: '9.5/10', info: { use: 'Those are your basic virtual machines — where you run app servers, batch jobs, anything that needs a server.', how: 'You pick an image, pick a size, it boots up, and we\'d usually put it behind an Auto Scaling Group and a load balancer so it scales and stays available.', where: 'Used it at Omnicell and Freddie Mac to run containerized and legacy workloads before we fully moved everything to EKS.' } },
  { name: 'S3', category: 'Cloud Platforms', years: '10+ years', rating: '9.5/10', info: { use: 'That\'s just object storage — logs, backups, build artifacts, static files, anything like that.', how: 'You drop files into buckets, and it handles versioning, lifecycle rules, and encryption for you.', where: 'At Mizuho I used it to hold our Terraform state, locked with DynamoDB, and at Omnicell we archived backups to S3 Glacier.' } },
  { name: 'Route53', category: 'Cloud Platforms', years: '10 years', rating: '9/10', info: { use: 'That\'s AWS\'s DNS service — points your domain to the right place and handles failover.', how: 'You set up routing policies — weighted, failover, latency-based — so traffic goes where you want, or fails over automatically if something\'s down.', where: 'Used it at State of Tennessee for our disaster recovery failover, and at Freddie Mac for weighted routing during blue-green releases.' } },
  { name: 'RDS', category: 'Cloud Platforms', years: '10 years', rating: '9/10', info: { use: 'That\'s managed relational databases — MySQL, Postgres, Oracle, whatever you need.', how: 'AWS handles the patching, backups, and Multi-AZ failover for you, so you\'re not babysitting the database yourself.', where: 'Ran Oracle and Postgres on RDS at Freddie Mac, and set up Multi-AZ failover for it at State of Tennessee.' } },
  { name: 'Lambda', category: 'Cloud Platforms', years: '8 years', rating: '8.5/10', info: { use: 'Serverless functions — you write the code, and it just runs when something triggers it, no server to manage.', how: 'It kicks off from events — an S3 upload, an SQS message, an API call — and scales automatically without you provisioning anything.', where: 'Used it at Mizuho for trade reconciliation workflows, and at State of Tennessee for auto-remediating non-compliant AWS resources.' } },
  { name: 'CloudFront', category: 'Cloud Platforms', years: '10 years', rating: '8.5/10', info: { use: 'That\'s AWS\'s CDN — caches your content closer to users so pages load faster.', how: 'It sits in front of S3 or your load balancer and serves cached content from edge locations, and you can bolt WAF onto it for security.', where: 'Used it at State of Tennessee for citizen-facing sites, and at Omnicell and Freddie Mac in front of our load balancers.' } },
  { name: 'Azure (general)', category: 'Cloud Platforms', years: '8 years', rating: '8.5/10', info: { use: 'That\'s Microsoft\'s cloud — I use it when we\'re running multi-cloud alongside AWS.', how: 'Same general idea as AWS — VMs, managed Kubernetes, identity — just through the Azure Portal, CLI, and ARM/Bicep instead.', where: 'Used it at Mizuho, where we ran a real multi-cloud setup across AWS and Azure for the banking platforms.' } },
  { name: 'GCP (general)', category: 'Cloud Platforms', years: '6 years', rating: '7.5/10', info: { use: 'That\'s Google\'s cloud — mostly came up for me around GKE and container workloads.', how: 'Same general idea, just Google\'s flavor — Compute Engine, GKE, Cloud Functions, managed through the gcloud CLI.', where: 'Honestly that\'s more from my own hands-on learning than a specific client project — I haven\'t had a GCP-primary engagement yet.' } },
  { name: 'GCE (Compute Engine)', category: 'Cloud Platforms', years: '5 years', rating: '7/10', info: { use: 'That\'s just Google\'s version of EC2 — plain virtual machines.', how: 'You pick a machine type, boot it up, and use managed instance groups if you need autoscaling.', where: 'Same as GCP overall — that\'s from my own hands-on exposure, not tied to a specific client project.' } },
  { name: 'Cloud Functions', category: 'Cloud Platforms', years: '5 years', rating: '7/10', info: { use: 'Google\'s version of Lambda — serverless functions triggered by events.', how: 'You write a function, hook it up to a trigger like Pub/Sub or HTTP, and it runs without you managing infrastructure.', where: 'Same story — GCP exposure from my own learning, not a dedicated client project yet.' } },

  // Infrastructure as Code
  { name: 'AWS CloudFormation', category: 'Infrastructure as Code', years: '9 years', rating: '9/10', info: { use: 'It\'s AWS\'s own infrastructure-as-code tool — same idea as Terraform, just AWS-native.', how: 'You write a YAML or JSON template describing your resources, and it stands them up as a Stack, with automatic rollback if something breaks.', where: 'Used it alongside Terraform at Mizuho with StackSets, and at Omnicell for our multi-account HIPAA setup.' } },
  { name: 'ARM/Bicep', category: 'Infrastructure as Code', years: '4 years', rating: '8/10', info: { use: 'That\'s how you write infrastructure as code specifically for Azure.', how: 'Bicep is basically a cleaner syntax that compiles down to ARM templates, and you deploy it through the CLI or a pipeline.', where: 'Used it at Mizuho to keep our Azure infrastructure just as version-controlled as our Terraform-managed AWS side.' } },
  { name: 'Terraform', category: 'Infrastructure as Code', years: '8 years', rating: '9.5/10', info: { use: 'That\'s my main infrastructure-as-code tool — I use it to stand up and manage pretty much everything in the cloud.', how: 'You write your infrastructure in HCL, it plans the changes, applies them, and tracks everything in a state file — I keep that remotely in S3 with a DynamoDB lock.', where: 'Core tool at every job I\'ve had — built a reusable module library at Mizuho, and ran multi-environment workspaces at Omnicell.' } },
  { name: 'Ansible', category: 'Infrastructure as Code', years: '8 years', rating: '9/10', info: { use: 'Configuration management — enforces the state you want across a fleet of servers.', how: 'It\'s agentless, so it just SSHes in and runs playbooks written in YAML to configure things idempotently.', where: 'Used it at State of Tennessee for provisioning and patching, and at Freddie Mac through Ansible Tower for CIS hardening.' } },
  { name: 'Packer', category: 'Infrastructure as Code', years: '7 years', rating: '8/10', info: { use: 'It builds machine images — so you\'re deploying a pre-baked, consistent image instead of configuring servers after they boot.', how: 'It spins up a temp instance, runs your provisioning scripts on it, then bakes the result into an AMI.', where: 'That\'s part of the IaC toolchain alongside Terraform and Ansible — standard tool, not tied to one specific project.' } },
  { name: 'HashiCorp Vault', category: 'Infrastructure as Code', years: '7 years', rating: '8.5/10', info: { use: 'Centralized secrets management, but with dynamic, short-lived credentials instead of static ones.', how: 'It generates secrets on demand — like database credentials — that automatically expire after a set time.', where: 'Implemented it at Mizuho specifically to get rid of hardcoded credentials across our pipelines.' } },
  { name: 'Chef', category: 'Infrastructure as Code', years: '7 years', rating: '7/10', info: { use: 'Another configuration management tool, similar to Ansible, but agent-based.', how: 'You write cookbooks describing the desired state, and a Chef client on each node pulls that config and applies it.', where: 'Used it at Freddie Mac, alongside Ansible Tower, for hardening servers against CIS benchmarks.' } },

  // Networking
  { name: 'VPC', category: 'Networking', years: '10 years', rating: '9.5/10', info: { use: 'That\'s your private network in the cloud — where you control subnets, routing, and who can talk to what.', how: 'You carve out subnets, set up route tables and gateways, and lock things down with security groups.', where: 'Every single project I\'ve worked on — Mizuho, State of Tennessee, Omnicell, Freddie Mac — starts with a VPC.' } },
  { name: 'ELB/ALB/NLB', category: 'Networking', years: '10 years', rating: '9/10', info: { use: 'Load balancers — they spread traffic across your servers so nothing gets overwhelmed and one bad instance doesn\'t take you down.', how: 'ALB works at the application layer for HTTP with routing rules; NLB handles raw high-throughput TCP; both do health checks and work with Auto Scaling.', where: 'Used ELB for blue-green weighted routing at Freddie Mac, and ALBs in front of our containers at State of Tennessee and Omnicell.' } },
  { name: 'API Gateway', category: 'Networking', years: '8 years', rating: '8.5/10', info: { use: 'That\'s the front door for your APIs when you\'re going serverless.', how: 'It handles routing, throttling, and auth, and plugs straight into Lambda on the backend.', where: 'Used it at State of Tennessee for our citizen-facing APIs, alongside ALB and CloudFront.' } },
  { name: 'Transit Gateway', category: 'Networking', years: '6 years', rating: '7.5/10', info: { use: 'It\'s basically a hub that connects all your VPCs and on-prem networks together instead of a messy peering setup.', how: 'Everything attaches to the hub, and it routes traffic between them centrally.', where: 'That one\'s more from the skill set — came up in multi-VPC architecture work, not a single standout project.' } },
  { name: 'Azure Application Gateway', category: 'Networking', years: '6 years', rating: '7.5/10', info: { use: 'Azure\'s version of an application load balancer, with a WAF built in.', how: 'Routes HTTP traffic based on path or host, terminates SSL, and can block bad traffic at the edge.', where: 'Used it at Mizuho alongside AKS to route traffic into our Azure-hosted services.' } },

  // Security & DevSecOps
  { name: 'IAM', category: 'Security & DevSecOps', years: '10 years', rating: '9.5/10', info: { use: 'That\'s how you control who — or what service — can do what in your AWS account.', how: 'You write policies that grant just the permissions needed, nothing more, and attach them to users or roles.', where: 'Least-privilege IAM was something I enforced at every shop, but it was a real focus at State of Tennessee for FedRAMP and at Freddie Mac for GSE compliance.' } },
  { name: 'GuardDuty', category: 'Security & DevSecOps', years: '8 years', rating: '8.5/10', info: { use: 'It\'s AWS\'s threat detection — watches for suspicious activity automatically.', how: 'It analyzes your CloudTrail, VPC flow logs, and DNS logs against threat intel and flags anything that looks off.', where: 'Used it at Mizuho and State of Tennessee as part of our overall security posture, alongside Security Hub and Config Rules.' } },
  { name: 'KMS', category: 'Security & DevSecOps', years: '8 years', rating: '9/10', info: { use: 'That\'s encryption key management — keeps your data encrypted at rest and in transit.', how: 'You create keys, AWS handles rotation, and you use them to encrypt things like S3, RDS, and Secrets Manager.', where: 'Used it at Mizuho for key lifecycle management, and at Omnicell to keep our PHI data encrypted for HIPAA.' } },
  { name: 'WAF', category: 'Security & DevSecOps', years: '8 years', rating: '8/10', info: { use: 'Web Application Firewall — blocks the common attacks, like SQL injection and XSS, before they hit your app.', how: 'You put it in front of CloudFront or your load balancer and apply rule sets that filter bad requests.', where: 'Used it at State of Tennessee to protect our citizen-facing sites.' } },
  { name: 'Shield', category: 'Security & DevSecOps', years: '8 years', rating: '8/10', info: { use: 'That\'s AWS\'s DDoS protection.', how: 'The standard tier is on automatically for things like CloudFront and Route 53, and it pairs with WAF for layer 7 attacks.', where: 'That\'s part of the standard AWS security stack we ran — baseline protection alongside WAF and GuardDuty, not a standalone project.' } },
  { name: 'AWS Config Rules', category: 'Security & DevSecOps', years: '7 years', rating: '8/10', info: { use: 'It continuously checks your AWS resources against your compliance rules and flags — or fixes — anything out of line.', how: 'You define rules, it evaluates your resources against them, and you can wire up a Lambda to auto-remediate when something drifts.', where: 'Used it at State of Tennessee for NIST and FedRAMP compliance with auto-remediation, and at Freddie Mac for GSE regulatory controls.' } },
  { name: 'Secrets Manager', category: 'Security & DevSecOps', years: '6 years', rating: '8.5/10', info: { use: 'Where you store credentials and API keys instead of hardcoding them anywhere.', how: 'It encrypts secrets with KMS and can automatically rotate things like database passwords.', where: 'That\'s the AWS-native option we had alongside Vault — standard tool in the toolkit rather than a headline project.' } },
  { name: 'Security Hub', category: 'Security & DevSecOps', years: '5 years', rating: '8/10', info: { use: 'It\'s a dashboard that pulls all your security findings into one place.', how: 'It aggregates stuff from GuardDuty, Inspector, and Config, and scores you against standards like CIS or NIST.', where: 'Used it at State of Tennessee and Freddie Mac as part of meeting FedRAMP and GSE security requirements.' } },
  { name: 'Inspector', category: 'Security & DevSecOps', years: '7 years', rating: '7.5/10', info: { use: 'It scans your EC2 instances and container images for known vulnerabilities.', how: 'It checks for CVEs and network exposure issues, and sends what it finds into Security Hub.', where: 'Used it at State of Tennessee alongside Config and GuardDuty for ongoing vulnerability management.' } },
  { name: 'SonarQube', category: 'Security & DevSecOps', years: '6 years', rating: '8.5/10', info: { use: 'Static code analysis — catches bugs, bad code smells, and security issues before code ships.', how: 'It scans your code on every build and can block the pipeline if quality drops below a threshold.', where: 'Had it wired into our Jenkins and GitHub Actions pipelines at Mizuho and Omnicell as a quality gate.' } },
  { name: 'Trivy', category: 'Security & DevSecOps', years: '4 years', rating: '8/10', info: { use: 'It\'s a vulnerability scanner for containers and infrastructure code.', how: 'It checks your container images and Terraform or Kubernetes manifests for known CVEs and misconfigurations before you deploy.', where: 'Used it at Omnicell alongside ECR scanning to catch container vulnerabilities before they hit production.' } },
  { name: 'Snyk', category: 'Security & DevSecOps', years: '4 years', rating: '7.5/10', info: { use: 'Similar idea — scans your dependencies and containers for known vulnerabilities.', how: 'It checks your package manifests against a vulnerability database and can suggest or auto-apply fixes.', where: 'That was part of our broader DevSecOps toolchain — standard tool alongside Trivy and Checkov, not a standalone story.' } },
  { name: 'Checkov', category: 'Security & DevSecOps', years: '4 years', rating: '7.5/10', info: { use: 'Scans your Terraform and CloudFormation code for misconfigurations before you ever deploy it.', how: 'It checks your IaC against built-in policy rules — CIS benchmarks and best practices — and fails the build if something\'s wrong.', where: 'Part of the DevSecOps pipeline for catching bad IaC before it shipped — standard tooling, not a headline project.' } },
  { name: 'OPA (Policy as Code)', category: 'Security & DevSecOps', years: '5 years', rating: '7.5/10', info: { use: 'It\'s a policy engine — you write rules, and it blocks anything that doesn\'t comply.', how: 'You write policies in Rego, and it evaluates them against Kubernetes admission requests or Terraform plans.', where: 'Used it at Mizuho and State of Tennessee to enforce Kubernetes RBAC and infrastructure policy as part of DevSecOps.' } },
  { name: 'OWASP Dependency-Check', category: 'Security & DevSecOps', years: '5 years', rating: '7/10', info: { use: 'Scans your app\'s dependencies for known vulnerabilities.', how: 'It cross-checks your dependency list against the national vulnerability database during the build.', where: 'Used it at Omnicell as part of the DevSecOps pipeline, alongside SonarQube and Trivy.' } },

  // CI/CD & DevOps Tools
  { name: 'Jenkins', category: 'CI/CD & DevOps Tools', years: '10 years', rating: '9.5/10', info: { use: 'That\'s my go-to CI/CD tool — runs the build, test, and deploy pipelines.', how: 'You write pipelines as code in a Jenkinsfile, and it runs them across a master and a pool of agents; Shared Libraries let you reuse pipeline logic across teams.', where: 'Primary CI/CD engine at every job — built out Shared Library frameworks at Mizuho and Freddie Mac.' } },
  { name: 'GitLab CI/CD', category: 'CI/CD & DevOps Tools', years: '7 years', rating: '9/10', info: { use: 'CI/CD that\'s built right into GitLab, so your pipeline lives next to your code.', how: 'You define stages in a .gitlab-ci.yml file, and GitLab Runners execute them — build, test, scan, deploy.', where: 'Used it at State of Tennessee to run pipelines across 20-plus state applications.' } },
  { name: 'GitHub Actions', category: 'CI/CD & DevOps Tools', years: '5 years', rating: '8.5/10', info: { use: 'CI/CD triggered straight off GitHub events — push, PR, whatever.', how: 'You write workflows in YAML, and they run on GitHub-hosted or self-hosted runners.', where: 'Built reusable composite workflows at Mizuho, and used it for CI/CD automation at Omnicell.' } },
  { name: 'Azure DevOps', category: 'CI/CD & DevOps Tools', years: '6 years', rating: '8.5/10', info: { use: 'Microsoft\'s all-in-one — pipelines, boards, repos.', how: 'You write pipelines in YAML, and it can deploy to Azure or AWS, with Boards for tracking work.', where: 'Used it at Mizuho alongside Jenkins and GitHub Actions for our multi-stage pipelines.' } },
  { name: 'CodePipeline/CodeBuild/CodeDeploy', category: 'CI/CD & DevOps Tools', years: '8 years', rating: '8.5/10', info: { use: 'That\'s AWS\'s own CI/CD suite, if you want to stay fully native.', how: 'CodePipeline orchestrates the stages, CodeBuild compiles and tests, and CodeDeploy handles the actual rollout, including blue-green.', where: 'Used it at Omnicell for our SaaS CI/CD and for blue-green and canary deployments.' } },
  { name: 'CircleCI', category: 'CI/CD & DevOps Tools', years: '5 years', rating: '7/10', info: { use: 'Another cloud CI/CD option, similar to Jenkins or GitHub Actions.', how: 'Pipelines run in Docker executors, and it\'s pretty good about caching and parallelizing jobs to keep builds fast.', where: 'That\'s more from the skill set than a specific project — we standardized on Jenkins and GitLab at most shops.' } },
  { name: 'Maven', category: 'CI/CD & DevOps Tools', years: '8 years', rating: '8/10', info: { use: 'Build tool for Java projects — handles dependencies and packaging.', how: 'You define your dependencies and build steps in a pom.xml, and it runs the whole lifecycle — compile, test, package.', where: 'Used it in our Jenkins pipelines for legacy Java apps at State of Tennessee and Freddie Mac.' } },
  { name: 'Gradle', category: 'CI/CD & DevOps Tools', years: '6 years', rating: '7.5/10', info: { use: 'Another Java build tool — faster and more flexible than Maven.', how: 'Build logic is written in Groovy or Kotlin, with incremental builds that speed up CI.', where: 'That\'s part of the build toolchain alongside Maven — general exposure rather than one flagship project.' } },
  { name: 'JFrog Artifactory / X-Ray', category: 'CI/CD & DevOps Tools', years: '6 years', rating: '7.5/10', info: { use: 'Stores your build artifacts, and X-Ray scans them for vulnerabilities.', how: 'Artifactory holds your JARs, Docker images, whatever you build, and X-Ray continuously checks them against known CVEs.', where: 'That\'s part of the artifact management layer, alongside Nexus — standard tooling rather than a specific story.' } },
  { name: 'Nexus', category: 'CI/CD & DevOps Tools', years: '6 years', rating: '8/10', info: { use: 'Artifact repository — where your build outputs and dependencies live.', how: 'It proxies and caches things like Maven Central, and also hosts your own internal releases.', where: 'Used it at State of Tennessee and Freddie Mac as our internal repo for Java build artifacts.' } },

  // Containers & Orchestration
  { name: 'Docker', category: 'Containers & Orchestration', years: '9 years', rating: '9/10', info: { use: 'Packages up your app with everything it needs so it runs the same anywhere.', how: 'You write a Dockerfile, build an image layer by layer, and run it as an isolated container.', where: 'Used it to containerize over 30 microservices at Mizuho, and 12 legacy .NET and Java apps at State of Tennessee.' } },
  { name: 'Kubernetes', category: 'Containers & Orchestration', years: '8 years', rating: '9.5/10', info: { use: 'Orchestrates your containers — deploys them, scales them, keeps them running.', how: 'It schedules containers onto a cluster of nodes and manages state through Deployments and Services.', where: 'Core platform at every job, via EKS or AKS — managed multi-tenant namespaces with RBAC at each one.' } },
  { name: 'Amazon EKS', category: 'Containers & Orchestration', years: '6 years', rating: '9.5/10', info: { use: 'AWS\'s managed Kubernetes — you don\'t run the control plane yourself.', how: 'AWS handles the control plane and etcd, you just run worker nodes, and it ties into IAM for auth.', where: 'Used it at Mizuho, State of Tennessee, Omnicell, and Freddie Mac — that\'s been my main Kubernetes platform.' } },
  { name: 'AKS', category: 'Containers & Orchestration', years: '5 years', rating: '8.5/10', info: { use: 'Same idea, but on Azure.', how: 'Azure runs the control plane, your node pools are VM scale sets, and it integrates with Azure AD for access.', where: 'Used it at Mizuho for the Azure side of our multi-cloud Kubernetes setup.' } },
  { name: 'GKE', category: 'Containers & Orchestration', years: '6 years', rating: '8/10', info: { use: 'Google\'s managed Kubernetes.', how: 'Same pattern — Google runs the control plane, you run node pools on Compute Engine.', where: 'That\'s from the skill set, not a specific client engagement — I know it well but haven\'t run it in production for a client yet.' } },
  { name: 'Helm', category: 'Containers & Orchestration', years: '7 years', rating: '9/10', info: { use: 'Package manager for Kubernetes — packages up your app so you can deploy it as one unit.', how: 'You define a Chart with templated manifests, and Helm installs, upgrades, or rolls it back as a single release.', where: 'Used it at Mizuho, State of Tennessee, and Omnicell to deploy our apps to EKS and AKS.' } },
  { name: 'Kustomize', category: 'Containers & Orchestration', years: '5 years', rating: '8.5/10', info: { use: 'Manages Kubernetes config differences across environments without templating.', how: 'You start with a base manifest and layer environment-specific patches on top at apply time.', where: 'Used it at State of Tennessee alongside ArgoCD to manage config across environments.' } },
  { name: 'ArgoCD', category: 'Containers & Orchestration', years: '5 years', rating: '9/10', info: { use: 'GitOps for Kubernetes — your Git repo becomes the source of truth for what\'s running.', how: 'It watches your repo and continuously syncs the cluster to match, so if something drifts, it corrects it.', where: 'Used it at State of Tennessee to run GitOps deployments to EKS.' } },
  { name: 'FluxCD', category: 'Containers & Orchestration', years: '4 years', rating: '8.5/10', info: { use: 'Similar to ArgoCD — another GitOps tool.', how: 'It watches your Git repo and image registries and reconciles cluster state automatically.', where: 'That\'s more alongside ArgoCD in the toolkit — familiar with it, but ArgoCD is what we standardized on.' } },
  { name: 'OpenShift / ROSA', category: 'Containers & Orchestration', years: '5 years', rating: '7/10', info: { use: 'Red Hat\'s enterprise flavor of Kubernetes — ROSA is that, but managed on AWS.', how: 'Same Kubernetes core, but with extra developer tooling, built-in CI/CD, and security policy baked in.', where: 'That one\'s from the skill matrix — enterprise Kubernetes exposure alongside EKS, AKS, GKE.' } },
  { name: 'Docker Swarm', category: 'Containers & Orchestration', years: '5 years', rating: '7/10', info: { use: 'Docker\'s own lightweight orchestrator, an alternative to Kubernetes.', how: 'It clusters a bunch of Docker hosts together and schedules services across them.', where: 'Had some exposure to it earlier on before we standardized fully on Kubernetes.' } },
  { name: 'Istio', category: 'Containers & Orchestration', years: '5 years', rating: '7.5/10', info: { use: 'Service mesh — handles traffic, security, and observability between your microservices.', how: 'It injects sidecar proxies into your pods that handle things like mTLS and retries without touching your app code.', where: 'That\'s part of the Kubernetes toolchain — familiar with it from the skill matrix, not a headline project.' } },
  { name: 'Linkerd', category: 'Containers & Orchestration', years: '4 years', rating: '6.5/10', info: { use: 'Lighter-weight service mesh, an alternative to Istio.', how: 'Uses smaller, faster proxies, so it\'s less overhead than Istio.', where: 'Same story — additional service mesh exposure alongside Istio.' } },

  // Monitoring & Observability
  { name: 'Prometheus', category: 'Monitoring & Observability', years: '7 years', rating: '9/10', info: { use: 'Collects metrics from your infrastructure and apps and alerts you when something\'s off.', how: 'It pulls metrics from your services on a schedule, stores them as time series, and fires alerts through Alertmanager.', where: 'Used it at Mizuho, State of Tennessee, and Omnicell for cluster and application metrics.' } },
  { name: 'Grafana', category: 'Monitoring & Observability', years: '8 years', rating: '9/10', info: { use: 'Turns your metrics into dashboards you can actually look at.', how: 'You point it at data sources like Prometheus or CloudWatch, and build dashboards and alerts on top.', where: 'Built custom SLI/SLO dashboards with it at Mizuho, and cluster health dashboards at Omnicell.' } },
  { name: 'Splunk', category: 'Monitoring & Observability', years: '6 years', rating: '8.5/10', info: { use: 'Enterprise log aggregation and SIEM — good for security monitoring at scale.', how: 'It ingests and indexes logs from everywhere, and you search and correlate with SPL to catch security events.', where: 'Set it up at Freddie Mac for SIEM correlation searches and automated security alerts.' } },
  { name: 'ELK Stack', category: 'Monitoring & Observability', years: '7 years', rating: '8.5/10', info: { use: 'Log aggregation and search — Elasticsearch, Logstash, Kibana.', how: 'Logstash ingests and parses your logs, Elasticsearch indexes them so you can search, and Kibana gives you the visual layer.', where: 'Used it at State of Tennessee and Freddie Mac to centralize logs across 200-plus applications.' } },
  { name: 'CloudWatch', category: 'Monitoring & Observability', years: '9 years', rating: '8.5/10', info: { use: 'AWS\'s built-in monitoring — metrics, logs, alarms.', how: 'It automatically collects metrics and logs from your AWS services, and you set alarms on top of thresholds.', where: 'Used it at Mizuho for observability, and at Freddie Mac with Logs Insights for our SLA dashboards.' } },
  { name: 'Azure Monitor', category: 'Monitoring & Observability', years: '7 years', rating: '8/10', info: { use: 'Same idea as CloudWatch, but for Azure.', how: 'It pulls metrics and logs into a Log Analytics workspace, and you query it with KQL.', where: 'That\'s the Azure counterpart we used at Mizuho, alongside CloudWatch on the AWS side.' } },
  { name: 'Datadog', category: 'Monitoring & Observability', years: '6 years', rating: '8/10', info: { use: 'A SaaS observability platform — metrics, traces, logs all in one place.', how: 'You install an agent, it ships everything to Datadog\'s backend, and you get correlated dashboards and APM out of the box.', where: 'Used it at Mizuho as part of our broader observability stack alongside Prometheus and Grafana.' } },
  { name: 'PagerDuty', category: 'Monitoring & Observability', years: '6 years', rating: '7.5/10', info: { use: 'Handles incident alerting and on-call rotations.', how: 'It routes alerts from your monitoring tools into escalation policies so the right person gets paged.', where: 'Part of the incident response layer we had running — standard tool alongside Prometheus and Datadog.' } },
  { name: 'OpenTelemetry', category: 'Monitoring & Observability', years: '4 years', rating: '7.5/10', info: { use: 'A standard way to instrument your apps for traces, metrics, and logs, so you\'re not locked into one vendor.', how: 'You instrument with the OTel SDK, and it exports to whatever backend you\'re using — Jaeger, Datadog, anything.', where: 'That\'s the instrumentation layer feeding our observability stack — familiar with it, standard tooling.' } },
  { name: 'Jaeger', category: 'Monitoring & Observability', years: '4 years', rating: '7/10', info: { use: 'Distributed tracing — helps you find where latency or failures are happening across microservices.', how: 'It collects trace spans as a request moves through your services and visualizes the whole path.', where: 'Tracing backend alongside OpenTelemetry — part of the toolkit.' } },
  { name: 'Fluentd', category: 'Monitoring & Observability', years: '5 years', rating: '7/10', info: { use: 'Log shipper — collects logs and forwards them wherever you need.', how: 'It tails logs from different sources, buffers them, and routes them to something like Elasticsearch or S3.', where: 'Alternative to Logstash in the ELK pipeline — standard tool, not a standalone story.' } },

  // Messaging
  { name: 'Kafka', category: 'Messaging', years: '5 years', rating: '8/10', info: { use: 'Event streaming — good for high-throughput, real-time data pipelines.', how: 'Producers publish to topics, consumers read them in order, and it\'s built to handle a ton of throughput reliably.', where: 'That\'s from the skill set for event-driven workloads — alongside SNS/SQS, which is what we mostly used on AWS projects.' } },
  { name: 'RabbitMQ', category: 'Messaging', years: '5 years', rating: '8/10', info: { use: 'A traditional message broker for queuing between services.', how: 'Uses AMQP — messages go through exchanges into queues, and consumers pick them up with delivery guarantees.', where: 'Alternative to SNS/SQS in the messaging toolkit — general exposure, not tied to one project.' } },
  { name: 'SNS / SQS', category: 'Messaging', years: '9 years', rating: '8.5/10', info: { use: 'AWS\'s messaging services — SNS for pub/sub, SQS for queuing.', how: 'SNS fans a message out to multiple subscribers, and SQS buffers messages so consumers can process them reliably at their own pace.', where: 'Used them at Mizuho for event-driven trade reconciliation, and at Omnicell for automating RDS snapshot cleanup.' } },

  // Scripting & Languages
  { name: 'Python', category: 'Scripting & Languages', years: '8 years', rating: '8.5/10', info: { use: 'My go-to for automation scripts and tooling.', how: 'Mostly used it with boto3 to talk to AWS — writing scripts for deployment validation, health checks, that kind of thing.', where: 'Used it at Omnicell and Freddie Mac for deployment validation, backup verification, and DR failover testing.' } },
  { name: 'Bash', category: 'Scripting & Languages', years: '10+ years', rating: '9/10', info: { use: 'Shell scripting — automates Linux tasks and glues pipeline steps together.', how: 'Just chaining CLI commands and logic into scripts, run directly or as steps inside a pipeline.', where: 'Used it everywhere — every job I\'ve had leans on Bash for pipeline glue and server automation.' } },
  { name: 'PowerShell', category: 'Scripting & Languages', years: '8 years', rating: '8/10', info: { use: 'Same idea as Bash, but for Windows and Azure.', how: 'It\'s object-oriented rather than plain text, and the Az modules let you script Azure resources directly.', where: 'That\'s for Windows Server administration — part of the toolkit alongside Linux and Bash.' } },
  { name: 'Groovy', category: 'Scripting & Languages', years: '7 years', rating: '7.5/10', info: { use: 'The scripting language behind Jenkins pipelines.', how: 'You write your Jenkinsfiles and Shared Library functions in it to define your pipeline logic.', where: 'Used it at Mizuho and Freddie Mac to build out our Jenkins Shared Library frameworks.' } },
  { name: 'Ruby', category: 'Scripting & Languages', years: '4 years', rating: '6/10', info: { use: 'Mainly came up for me through Chef.', how: 'Chef cookbooks are written in a Ruby-based DSL that describes the config you want.', where: 'Used it indirectly at Freddie Mac through Chef cookbooks for OS hardening.' } },
  { name: 'Go (Golang)', category: 'Scripting & Languages', years: '2-3 years', rating: '7/10', info: { use: 'Getting more into it since it\'s what most of the Kubernetes ecosystem is built in.', how: 'It\'s statically typed and compiles to a single binary, so it\'s great for small, fast CLI tools.', where: 'That\'s a newer one for me — a couple years writing small internal tools, not a primary language on any one project yet.' } },

  // Version Control & Collab
  { name: 'Git', category: 'Version Control & Collab', years: '10+ years', rating: '9.5/10', info: { use: 'Version control — tracks every change to code and infrastructure.', how: 'You commit locally, branch for features, and merge through pull requests, synced up to a remote like GitHub or GitLab.', where: 'Used it at every job for Terraform modules, Jenkinsfiles, application code — everything.' } },
  { name: 'GitHub', category: 'Version Control & Collab', years: '10 years', rating: '9/10', info: { use: 'Where the code lives, plus pull request reviews and Actions for CI/CD.', how: 'You get branch protection, PR review workflows, and it plugs straight into GitHub Actions.', where: 'Used it as our main Git host at Mizuho and Omnicell, tied into GitHub Actions.' } },
  { name: 'GitLab', category: 'Version Control & Collab', years: '7 years', rating: '8.5/10', info: { use: 'Similar to GitHub, but with CI/CD built right in.', how: 'Merge requests for review, and pipelines defined in a YAML file run by GitLab Runners.', where: 'Used it at State of Tennessee as our Git host and CI/CD platform for the state applications.' } },
  { name: 'Bitbucket', category: 'Version Control & Collab', years: '6 years', rating: '7/10', info: { use: 'Atlassian\'s Git hosting, usually paired with Jira.', how: 'Pull request workflows that tie directly into Jira tickets.', where: 'That\'s an additional option I\'ve used — alongside GitHub and GitLab, not tied to one specific engagement.' } },
  { name: 'Jira', category: 'Version Control & Collab', years: '10 years', rating: '9/10', info: { use: 'How we track sprints, stories, and tasks.', how: 'Kanban or Scrum boards, sprint planning, burndown charts — the usual Agile setup.', where: 'Used it at every job for sprint planning and tracking our DevOps and infrastructure work.' } },
  { name: 'Confluence', category: 'Version Control & Collab', years: '8 years', rating: '7.5/10', info: { use: 'Team wiki — where we kept documentation and runbooks.', how: 'Structured pages linked right to Jira tickets, so docs stay connected to the work.', where: 'Used it at Freddie Mac to write and maintain our incident response runbooks.' } },
  { name: 'ServiceNow', category: 'Version Control & Collab', years: '6 years', rating: '8/10', info: { use: 'IT service management — handles change requests and incident workflows.', how: 'Everything routes through configurable workflows tied to a CMDB, with approvals built in.', where: 'Used it at State of Tennessee for change management and incident tracking, with full audit documentation.' } },
  { name: 'MS Teams', category: 'Version Control & Collab', years: '5 years', rating: '7/10', info: { use: 'Team chat, plus it hooks into alerting.', how: 'You wire up webhooks from your monitoring or CI tools so alerts show up directly in a channel.', where: 'Used it alongside Jira and Confluence on the more Azure-heavy engagements.' } },

  // OS & Databases
  { name: 'Linux Administration', category: 'OS & Databases', years: '10+ years', rating: '9.5/10', info: { use: 'The OS running most of our production servers and containers.', how: 'Package management, systemd services, networking, hardening — the whole administration side, across RHEL, CentOS, Ubuntu.', where: 'Foundational everywhere I\'ve worked — hosting Jenkins agents, Kubernetes nodes, app servers, all of it.' } },
  { name: 'Windows Server', category: 'OS & Databases', years: '6 years', rating: '7/10', info: { use: 'For hosting legacy .NET applications.', how: 'Managing IIS, Active Directory integration, Windows services — the whole Windows admin side.', where: 'Used it at State of Tennessee and Omnicell to host legacy .NET apps alongside our Linux-based services.' } },
  { name: 'MySQL', category: 'OS & Databases', years: '8 years', rating: '8/10', info: { use: 'One of the relational databases we ran for application data.', how: 'Standard SQL database, usually managed through RDS so AWS handles replication and backups.', where: 'That\'s one of the RDS-hosted engines I\'ve managed — standard tooling across engagements.' } },
  { name: 'PostgreSQL', category: 'OS & Databases', years: '7 years', rating: '8/10', info: { use: 'Another relational database — usually my default pick for new development.', how: 'Same as MySQL — ran it through RDS with Multi-AZ for high availability.', where: 'Ran it at Freddie Mac, and set up Multi-AZ failover for it as part of the DR work at State of Tennessee.' } },
  { name: 'Oracle', category: 'OS & Databases', years: '6 years', rating: '7/10', info: { use: 'Enterprise database — usually for legacy, critical financial systems.', how: 'Handles large-scale relational workloads, with PL/SQL for the more complex logic, run through RDS for Oracle.', where: 'Ran it at Freddie Mac for the mortgage origination and servicing platform data.' } },
  { name: 'DynamoDB', category: 'OS & Databases', years: '7 years', rating: '8/10', info: { use: 'AWS\'s managed NoSQL database — good for high-scale, low-latency lookups.', how: 'Single-digit millisecond reads and writes, and it auto-scales throughput as you need it.', where: 'Used it at Mizuho as the lock table backing our Terraform remote state in S3.' } },
  { name: 'MongoDB', category: 'OS & Databases', years: '5 years', rating: '7/10', info: { use: 'Document database, for when your data doesn\'t fit neatly into tables.', how: 'Stores JSON-like documents in collections, and you can shard it horizontally as it grows.', where: 'That\'s from the broader NoSQL exposure alongside DynamoDB — general skill set, not a flagship project.' } },
  { name: 'Redis', category: 'OS & Databases', years: '5 years', rating: '8/10', info: { use: 'In-memory store — mostly for caching and session data.', how: 'Everything lives in memory so reads are sub-millisecond, which is great for caching query results or storing sessions.', where: 'Part of the caching layer alongside our RDS and DynamoDB setups — standard tooling.' } },

  // SRE & FinOps
  { name: 'Trusted Advisor / Cost Explorer', category: 'SRE & FinOps', years: '7 years', rating: '8/10', info: { use: 'How we kept an eye on cloud spend and found ways to cut costs.', how: 'Trusted Advisor flags stuff you can optimize, and Cost Explorer shows you spend trends so you can plan Reserved Instances or Savings Plans.', where: 'Used them at Mizuho and Omnicell to drive FinOps work that cut costs by 20 to 30 percent through tagging and RI planning.' } },
  { name: 'Gremlin (chaos engineering)', category: 'SRE & FinOps', years: '4 years', rating: '7/10', info: { use: 'Chaos engineering — you break things on purpose to make sure your systems actually recover.', how: 'You inject controlled failures, like latency or killing an instance, into a production-like environment and see how the system handles it.', where: 'Used it at Mizuho as part of our SRE practice, alongside tracking error budgets.' } },
];

const TECH_CATEGORIES = [...new Set(TECH_EXPERIENCE.map(t => t.category))];

function ScoreRing({ score, label, accent }) {
  const [display, setDisplay] = useState(0);
  const raf = useRef(null);
  const circumference = 2 * Math.PI * 38;

  useEffect(() => {
    if (raf.current) cancelAnimationFrame(raf.current);
    const start = performance.now();
    const duration = 900;
    const animate = (now) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - (1 - t) ** 3;
      setDisplay(Math.round(eased * score));
      if (t < 1) raf.current = requestAnimationFrame(animate);
    };
    raf.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf.current);
  }, [score]);

  const offset = circumference * (1 - display / 100);

  return (
    <div className="score-ring">
      <div className="ring-label">{label}</div>
      <div className="ring-visual">
        <svg viewBox="0 0 100 100" width="110" height="110">
          <circle cx="50" cy="50" r="38" className="ring-track" />
          <circle
            cx="50" cy="50" r="38"
            className="ring-progress"
            style={{ stroke: accent, strokeDasharray: circumference, strokeDashoffset: offset }}
            transform="rotate(-90 50 50)"
          />
        </svg>
        <div className="ring-value" style={{ color: accent }}>
          <span className="ring-num">{display}</span>
          <span className="ring-pct">%</span>
        </div>
      </div>
    </div>
  );
}

function FilmIcon() {
  return (
    <svg className="brand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="2" y="5" width="20" height="14" rx="1" />
      <line x1="2" y1="9" x2="22" y2="9" />
      <line x1="2" y1="15" x2="22" y2="15" />
      <line x1="6" y1="5" x2="6" y2="9" />
      <line x1="10" y1="5" x2="10" y2="9" />
      <line x1="14" y1="5" x2="14" y2="9" />
      <line x1="18" y1="5" x2="18" y2="9" />
      <line x1="6" y1="15" x2="6" y2="19" />
      <line x1="10" y1="15" x2="10" y2="19" />
      <line x1="14" y1="15" x2="14" y2="19" />
      <line x1="18" y1="15" x2="18" y2="19" />
    </svg>
  );
}

function EmptyResultsIcon() {
  return (
    <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
      <rect x="8" y="16" width="48" height="32" rx="1" strokeDasharray="5 3" />
      <line x1="8" y1="23" x2="56" y2="23" />
      <line x1="8" y1="41" x2="56" y2="41" />
      <circle cx="32" cy="32" r="6" />
      <circle cx="32" cy="32" r="2" fill="currentColor" stroke="none" />
    </svg>
  );
}

const HISTORY_PAGE_SIZE = 20;

export default function App() {
  // Navigation — persist in URL hash so refresh stays on the same page
  const [currentPage, setCurrentPageState] = useState(() => {
    const hash = window.location.hash.replace('#', '');
    return hash || 'command-center';
  });
  const setCurrentPage = (page) => {
    setCurrentPageState(page);
    window.location.hash = page === 'command-center' ? '' : page;
  };

  const [jdText, setJdText] = useState('');
  const [aiNotes, setAiNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);
  const [coverLetter, setCoverLetter] = useState(null);
  const [coverLetterPath, setCoverLetterPath] = useState(null);
  const [generatingCL, setGeneratingCL] = useState(false);
  
  const [infoAddresses, setInfoAddresses] = useState([]);
  const [addressSearchQuery, setAddressSearchQuery] = useState('');
  const [expSearchQuery, setExpSearchQuery] = useState('');
  const [expCategoryFilter, setExpCategoryFilter] = useState('All');
  const [expExpanded, setExpExpanded] = useState(() => new Set());
  const [telegramStatus, setTelegramStatus] = useState(null);

  useEffect(() => {
    if (currentPage === 'info') {
      fetch('http://localhost:8000/api/addresses')
        .then(res => res.json())
        .then(data => setInfoAddresses(data))
        .catch(err => console.error("Error fetching addresses:", err));
      fetch('http://localhost:8000/api/telegram/status')
        .then(res => res.json())
        .then(data => setTelegramStatus(data))
        .catch(() => setTelegramStatus({ configured: false }));
    }
  }, [currentPage]);
  const [copied, setCopied] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [storedResumes, setStoredResumes] = useState([]);
  const [selectedResumeName, setSelectedResumeName] = useState(() => localStorage.getItem('selectedResume') || null);
  const [uploadingResume, setUploadingResume] = useState(false);
  // Latest requested cover-letter/mail-draft record id — lets a slow request that
  // resolves after the user has already moved on (closed the modal, clicked a
  // different row) detect it's stale and skip reopening the modal with old data.
  const latestCLRequestId = useRef(null);
  const latestMailRequestId = useRef(null);
  const [loadingCLId, setLoadingCLId] = useState(null);
  const [historyCLModal, setHistoryCLModal] = useState(null);
  const [batchMode, setBatchMode] = useState(false);
  const [batchJds, setBatchJds] = useState(['']);
  const [batchJobs, setBatchJobs] = useState([]);
  const [batchRunning, setBatchRunning] = useState(false);
  // History search / filter / pagination / sort
  const [historySearch, setHistorySearch] = useState('');
  const [historyStatusFilter, setHistoryStatusFilter] = useState('');
  const [historyPage, setHistoryPage] = useState(1);
  const [historySortBy, setHistorySortBy] = useState('date');
  const [historySortDir, setHistorySortDir] = useState('desc');
  const [expandedJdId, setExpandedJdId] = useState(null);
  // Mail draft — results panel
  const [mailDraft, setMailDraft] = useState(null);
  const [generatingMail, setGeneratingMail] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [draftPath, setDraftPath] = useState(null);
  const [copiedField, setCopiedField] = useState(null);
  // Mail draft — history modal
  const [historyMailModal, setHistoryMailModal] = useState(null);
  const [loadingMailId, setLoadingMailId] = useState(null);
  const [historyDraftSaving, setHistoryDraftSaving] = useState(false);
  const [historyDraftPath, setHistoryDraftPath] = useState(null);
  // Active record for panels 03 + 04
  const [activeRecordId, setActiveRecordId] = useState(null);
  const [activeCompanyName, setActiveCompanyName] = useState(null);
  // Lets handleSelectRecord's async content fetch detect it's been superseded by a
  // newer selection before applying cover letter / mail draft / follow-up state.
  const activeRecordRequestRef = useRef(null);
  // Re-run an already-scanned JD — updates that record's tailored resume in place
  const [rerunRecordId, setRerunRecordId] = useState(null);
  const [rerunCompanyName, setRerunCompanyName] = useState(null);
  const [duplicateConflict, setDuplicateConflict] = useState(null);
  const [experienceConflict, setExperienceConflict] = useState(null);
  // Additional Points — add extra bullets to the current tailored resume
  const [addPointsText, setAddPointsText] = useState('');
  const [addPointsTarget, setAddPointsTarget] = useState('');
  const [addPointsLoading, setAddPointsLoading] = useState(false);
  const [addPointsSuccess, setAddPointsSuccess] = useState(null);
  // Personal profile
  const [profileText, setProfileText] = useState('');
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [profileUploading, setProfileUploading] = useState(false);
  const [profileUploadMsg, setProfileUploadMsg] = useState(null);
  // API Usage
  const [usageStats, setUsageStats] = useState(null);
  const [usageOpen, setUsageOpen] = useState(false);
  // Gmail integration
  const [gmailConnected, setGmailConnected] = useState(false);
  const [gmailEmail, setGmailEmail] = useState('');
  const [gmailCanOrganize, setGmailCanOrganize] = useState(false);
  const [savingToGmail, setSavingToGmail] = useState(false);
  const [gmailSaved, setGmailSaved] = useState(false);
  // Cross-page deep link: Inbox -> Command Center job workspace
  const [pendingCommandCenterJobId, setPendingCommandCenterJobId] = useState(null);
  // Follow-up mail
  const [followUpEmail, setFollowUpEmail] = useState('');
  const [followUpInstructions, setFollowUpInstructions] = useState('');
  const [followUpDraft, setFollowUpDraft] = useState(null);
  const [generatingFollowUp, setGeneratingFollowUp] = useState(false);
  const [savingFollowUp, setSavingFollowUp] = useState(false);
  const [followUpGmailSaved, setFollowUpGmailSaved] = useState(false);
  const [inboxMessages, setInboxMessages] = useState([]);
  const [inboxLoading, setInboxLoading] = useState(false);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [inboxSearch, setInboxSearch] = useState('');
  const [inboxError, setInboxError] = useState(null);
  const [selectedMsgId, setSelectedMsgId] = useState(null);
  const [loadingMsgId, setLoadingMsgId] = useState(null);
  // Follow-up attachments
  const [fuAttach, setFuAttach] = useState({ resume: false, cover_letter: false, dl: false, gc: false });
  const [personalDocs, setPersonalDocs] = useState({});
  const [uploadingDoc, setUploadingDoc] = useState(null);

  const fetchPersonalDocs = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/documents');
      const data = await res.json();
      if (res.ok) setPersonalDocs(data.documents || {});
    } catch { /* silent */ }
  };

  const handleUploadDoc = async (docType, file) => {
    if (!file) return;
    setUploadingDoc(docType);
    try {
      const fd = new FormData();
      fd.append('doc_type', docType);
      fd.append('file', file);
      const res = await fetch('http://localhost:8000/api/documents/upload', { method: 'POST', body: fd });
      if (res.ok) {
        await fetchPersonalDocs();
        setFuAttach(prev => ({ ...prev, [docType]: true }));
      } else {
        const data = await res.json();
        setError(data.detail || 'Upload failed');
      }
    } catch { setError('Failed to upload document.'); }
    finally { setUploadingDoc(null); }
  };

  const fetchResumes = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/resumes');
      if (!res.ok) return;
      const data = await res.json();
      setStoredResumes(data);
      if (data.length > 0) {
        const stored = localStorage.getItem('selectedResume');
        if (!data.some(r => r.filename === stored)) {
          setSelectedResumeName(data[0].filename);
          localStorage.setItem('selectedResume', data[0].filename);
        }
      }
    } catch { /* ignore */ }
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/history?limit=200');
      if (res.ok) setHistory(await res.json());
    } catch { /* ignore */ }
  };

  const checkGmailStatus = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/gmail/status');
      if (res.ok) {
        const data = await res.json();
        setGmailConnected(data.connected);
        setGmailEmail(data.email || '');
        setGmailCanOrganize(!!data.can_organize);
      }
    } catch { /* ignore */ }
  };

  const fetchUsage = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/usage');
      if (res.ok) setUsageStats(await res.json());
    } catch { /* ignore */ }
  };

  const fetchProfile = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/profile');
      if (res.ok) {
        const data = await res.json();
        setProfileText(data.content || '');
        setProfileLoaded(data.exists);
      }
    } catch { /* ignore */ }
  };

  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    fetchHistory();
    fetchResumes();
    checkGmailStatus();
    fetchProfile();
    fetchUsage();
    fetchPersonalDocs();

    const params = new URLSearchParams(window.location.search);
    if (params.get('gmail') === 'connected') {
      window.history.replaceState({}, '', window.location.pathname);
    }
  });

  // Derived history values — historyPage resets are computed, not effectful
  const filteredHistory = history
    .filter(item => !historySearch || (item.company_name || '').toLowerCase().includes(historySearch.toLowerCase()))
    .filter(item => !historyStatusFilter || item.status === historyStatusFilter)
    .sort((a, b) => {
      const dir = historySortDir === 'asc' ? 1 : -1;
      if (historySortBy === 'score') return (a.score - b.score) * dir;
      if (historySortBy === 'company') return (a.company_name || '').localeCompare(b.company_name || '') * dir;
      if (historySortBy === 'status') return (a.status || '').localeCompare(b.status || '') * dir;
      return ((a.created_at || '') < (b.created_at || '') ? -1 : 1) * dir;
    });
  const totalPages = Math.ceil(filteredHistory.length / HISTORY_PAGE_SIZE) || 1;
  const computedPage = historyPage > totalPages ? 1 : historyPage;
  const pagedHistory = filteredHistory.slice((computedPage - 1) * HISTORY_PAGE_SIZE, computedPage * HISTORY_PAGE_SIZE);

  const toggleSort = (field) => {
    if (historySortBy === field) setHistorySortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setHistorySortBy(field); setHistorySortDir('desc'); }
  };

  const handleSaveToGmail = async () => {
    if (!mailDraft || !activeRecordId) return;
    setSavingToGmail(true);
    setGmailSaved(false);
    try {
      const res = await fetch('http://localhost:8000/api/gmail/save-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to_emails: mailDraft.to_emails || [],
          subject: mailDraft.subject,
          body: mailDraft.body,
          record_id: activeRecordId,
        }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Failed to save to Gmail'); return; }
      setGmailSaved(true);
      setTimeout(() => setGmailSaved(false), 5000);
    } catch {
      setError('Failed to save draft to Gmail');
    } finally {
      setSavingToGmail(false);
    }
  };

  const handleDisconnectGmail = async () => {
    try {
      await fetch('http://localhost:8000/api/gmail/disconnect', { method: 'POST' });
      setGmailConnected(false);
      setGmailEmail('');
    } catch { /* ignore */ }
  };

  const handleSaveProfile = async () => {
    setProfileSaving(true);
    try {
      const res = await fetch('http://localhost:8000/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: profileText }),
      });
      if (res.ok) setProfileLoaded(true);
    } catch { /* ignore */ }
    finally { setProfileSaving(false); }
  };

  const handleProfileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setProfileUploading(true);
    setProfileUploadMsg(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('http://localhost:8000/api/profile/upload', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) { setProfileUploadMsg(data.detail || 'Upload failed'); return; }
      setProfileText(data.profile || '');
      setProfileLoaded(true);
      setProfileUploadMsg(data.message || 'Facts extracted and merged into profile.');
      setTimeout(() => setProfileUploadMsg(null), 5000);
    } catch {
      setProfileUploadMsg('Failed to process document.');
    } finally {
      setProfileUploading(false);
      e.target.value = '';
    }
  };

  const handleAddResume = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.docx')) { setError('Only .docx files are supported.'); return; }
    setUploadingResume(true);
    const formData = new FormData();
    formData.append('resume', file);
    try {
      const res = await fetch('http://localhost:8000/api/resumes', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Upload failed'); return; }
      await fetchResumes();
      setSelectedResumeName(data.filename);
      localStorage.setItem('selectedResume', data.filename);
    } catch {
      setError('Upload failed. Check your connection.');
    } finally {
      setUploadingResume(false);
    }
  };

  const handleResumeSelect = (filename) => {
    setSelectedResumeName(filename);
    localStorage.setItem('selectedResume', filename);
  };

  const handleResumeDelete = async (filename) => {
    try {
      const res = await fetch(`http://localhost:8000/api/resumes/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      if (res.ok) {
        const remaining = storedResumes.filter(r => r.filename !== filename);
        setStoredResumes(remaining);
        if (selectedResumeName === filename) {
          const next = remaining[0]?.filename || null;
          setSelectedResumeName(next);
          if (next) localStorage.setItem('selectedResume', next);
          else localStorage.removeItem('selectedResume');
        }
      }
    } catch (err) {
      console.error('Failed to delete resume:', err);
    }
  };

  const handleScan = async (overrideExperienceCheck = false) => {
    setError(null);
    setDuplicateConflict(null);
    if (!overrideExperienceCheck) setExperienceConflict(null);
    if (!jdText.trim()) { setError('Job Description is required.'); return; }
    if (!selectedResumeName && storedResumes.length === 0) { setError('Please add a base resume first.'); return; }
    setLoading(true);
    setResult(null);
    setCoverLetter(null);
    setCoverLetterPath(null);
    setMailDraft(null);
    setDraftPath(null);
    const formData = new FormData();
    formData.append('jd_text', jdText);
    if (aiNotes.trim()) formData.append('ai_notes', aiNotes.trim());
    if (selectedResumeName) formData.append('selected_resume', selectedResumeName);
    if (rerunRecordId) formData.append('rerun_id', rerunRecordId);
    if (overrideExperienceCheck) formData.append('override_experience_check', 'true');
    try {
      const res = await fetch('http://localhost:8000/api/scan', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 409 && data.detail?.duplicate_id) {
          setDuplicateConflict(data.detail);
          setError(data.detail.message);
        } else if (res.status === 409 && data.detail?.experience_conflict) {
          setExperienceConflict(data.detail);
          setError(data.detail.message);
        } else {
          setError(res.status === 429 ? 'Rate limit hit — wait a moment and try again.' : (data.detail || `Server error (${res.status}). Please try again.`));
        }
        return;
      }
      setExperienceConflict(null);
      setResult(data);
      setActiveRecordId(data.id);
      setActiveCompanyName(data.company_name);
      if (data.rerun) {
        setError(null);
      } else if (data.duplicate) {
        setError(`Note: ${data.company_name} was scanned before (previous score: ${data.previous_score}%). A new entry has been added.`);
      }
      setRerunRecordId(null);
      setRerunCompanyName(null);
      fetchHistory();
    } catch {
      setError('An error occurred. Check your connection or API limits.');
    } finally {
      setLoading(false); fetchUsage();
    }
  };

  const handleRerunFromLog = (item) => {
    setDuplicateConflict(null);
    setError(null);
    setJdText(item.jd_text || '');
    setRerunRecordId(item.id);
    setRerunCompanyName(item.company_name);
    handleSelectRecord(item);
    if (batchMode) setBatchMode(false);
    setTimeout(() => {
      document.getElementById('panel-pre-production')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
  };

  const handleAcceptDuplicateRerun = () => {
    if (!duplicateConflict?.duplicate_id) return;
    setRerunRecordId(duplicateConflict.duplicate_id);
    setRerunCompanyName(duplicateConflict.company_name);
    setDuplicateConflict(null);
    setError(null);
  };

  const handleAcceptExperienceOverride = () => {
    setExperienceConflict(null);
    setError(null);
    handleScan(true);
  };

  const handleReset = () => {
    setJdText('');
    setAiNotes('');
    setResult(null);
    setError(null);
    setCoverLetter(null);
    setCoverLetterPath(null);
    setMailDraft(null);
    setDraftPath(null);
    setActiveRecordId(null);
    setActiveCompanyName(null);
    setRerunRecordId(null);
    setRerunCompanyName(null);
    setDuplicateConflict(null);
    setExperienceConflict(null);
    setAddPointsText('');
    setAddPointsTarget('');
    setAddPointsSuccess(null);
    setFollowUpEmail('');
    setFollowUpDraft(null);
    setInboxMessages([]);
    setInboxOpen(false);
    setSelectedMsgId(null);
  };

  const handleDeleteHistory = async (id) => {
    if (!window.confirm('Delete this record?')) return;
    try {
      const res = await fetch(`http://localhost:8000/api/history/${id}`, { method: 'DELETE' });
      if (res.ok) fetchHistory();
    } catch (err) {
      console.error('Failed to delete record:', err);
    }
  };

    const handleSaveToApplications = async (job) => {
    try {
      const res = await fetch('http://localhost:8000/api/applications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company: job.company,
          title: job.title || '',
          url: job.url || '',
          source: 'command-center',
          status: 'Shortlisted',
          notes: job.url || ''
        }),
      });
      if (res.ok) {
        alert('Saved to applications!');
      } else {
        alert('Failed to save (check if backend supports /api/applications)');
      }
    } catch (err) {
      console.error('Failed to save to Applications:', err);
    }
  };

  const handleGenerateCL = async () => {
    if (!activeRecordId) { setError('Select a company first.'); return; }
    setGeneratingCL(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${activeRecordId}/cover-letter`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || `Error ${res.status}`); return; }
      setCoverLetter(data.cover_letter);
      setCoverLetterPath(data.cl_path || null);
    } catch {
      setError('Failed to generate cover letter. The AI provider might be overloaded.');
    } finally {
      setGeneratingCL(false); fetchUsage();
    }
  };

  const handleAddPoints = async () => {
    if (!activeRecordId) { setError('Run a scan first, or select a company from the Production Log.'); return; }
    if (!addPointsText.trim()) { setError('Enter at least one point to add.'); return; }
    setAddPointsLoading(true);
    setAddPointsSuccess(null);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${activeRecordId}/add-points`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ points: addPointsText.trim(), target_hint: addPointsTarget.trim() || undefined }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || `Error ${res.status}`); return; }
      setResult(prev => prev ? {
        ...prev,
        after_score: data.scan_result.after_score,
        replacements: data.scan_result.replacements,
        tailored: true,
      } : prev);
      setAddPointsSuccess(`Added ${data.inserted} point${data.inserted !== 1 ? 's' : ''} to the tailored resume.`);
      setAddPointsText('');
      setAddPointsTarget('');
      fetchHistory();
    } catch {
      setError('Failed to add points. Check your connection or try again.');
    } finally {
      setAddPointsLoading(false); fetchUsage();
    }
  };

  const handleHistoryCL = async (id, companyName) => {
    latestCLRequestId.current = id;
    setLoadingCLId(id);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${id}/cover-letter`, { method: 'POST' });
      const data = await res.json();
      if (latestCLRequestId.current !== id) return; // superseded by a newer request
      if (!res.ok) {
        setError(data.detail || `Failed to generate cover letter (${res.status})`);
        return;
      }
      setHistoryCLModal({ cover_letter: data.cover_letter, cl_path: data.cl_path, company_name: companyName });
    } catch {
      if (latestCLRequestId.current === id) setError('Failed to generate cover letter.');
    } finally {
      if (latestCLRequestId.current === id) setLoadingCLId(null);
    }
  };

  const handleStatusChange = async (id, newStatus) => {
    try {
      const res = await fetch(`http://localhost:8000/api/history/${id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) fetchHistory();
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  const handleBatchRun = async () => {
    if (storedResumes.length === 0 || !selectedResumeName) {
      setError('Batch mode requires a stored base resume. Add one in Single Scan mode first.');
      return;
    }
    const jds = batchJds.map(j => j.trim()).filter(j => j.length > 50);
    if (jds.length === 0) {
      setError('No valid JDs found. Each box needs at least 50 characters.');
      return;
    }
    setError(null);
    setBatchJobs(jds.map((jd, i) => ({ id: i, jd, status: 'processing', result: null, error: null })));
    setBatchRunning(true);
    try {
      const res = await fetch('http://localhost:8000/api/batch-scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jd_texts: jds, selected_resume: selectedResumeName, ai_notes: aiNotes.trim() || undefined }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || `Batch error (${res.status})`);
        setBatchJobs(prev => prev.map(j => ({ ...j, status: 'error', error: data.detail || 'Batch failed' })));
      } else {
        setBatchJobs(prev => prev.map((j, idx) => {
          const r = data.results.find(x => x.index === idx);
          if (!r) return { ...j, status: 'error', error: 'No result returned' };
          if (r.skipped) return { ...j, status: 'skipped', error: r.reason };
          return { ...j, status: 'done', result: r };
        }));
      }
    } catch {
      setBatchJobs(prev => prev.map(j => ({ ...j, status: 'error', error: 'Network error' })));
    }
    setBatchRunning(false);
    fetchHistory();
  };

  const handleBatchFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
      const text = ev.target.result || '';
      const parts = text.split(/\n[ \t]*---[ \t]*\n/).map(j => j.trim()).filter(Boolean);
      if (parts.length > 0) {
        setBatchJds(parts.slice(0, 10));
      } else {
        setBatchJds([text]);
      }
    };
    reader.readAsText(file);
  };

  const toggleJdExpand = (id) => setExpandedJdId(prev => prev === id ? null : id);

  const handleGenerateMail = async () => {
    if (!activeRecordId) { setError('Select a company first.'); return; }
    setGeneratingMail(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${activeRecordId}/mail-draft`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || `Mail draft error (${res.status})`); return; }
      setMailDraft(data);
      setDraftPath(null);
    } catch {
      setError('Failed to generate mail draft.');
    } finally {
      setGeneratingMail(false); fetchUsage();
    }
  };

  const handleSaveDraft = async () => {
    if (!activeRecordId || !mailDraft) return;
    setSavingDraft(true);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${activeRecordId}/mail-draft/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: mailDraft.subject, body: mailDraft.body }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Save failed'); return; }
      setDraftPath(data.draft_path);
    } catch {
      setError('Failed to save draft.');
    } finally {
      setSavingDraft(false);
    }
  };

  const handleSelectRecord = async (item) => {
    activeRecordRequestRef.current = item.id;
    setActiveRecordId(item.id);
    setActiveCompanyName(item.company_name);
    setAddPointsText('');
    setAddPointsTarget('');
    setAddPointsSuccess(null);
    setCoverLetter(null);
    setCoverLetterPath(null);
    setMailDraft(null);
    setDraftPath(null);
    setFollowUpEmail('');
    setFollowUpDraft(null);
    setInboxMessages([]);
    setInboxOpen(false);
    setSelectedMsgId(null);

    // Populate Post-Production panel with this record's stored scan data
    const sr = item.scan_result || {};
    setResult({
      id: item.id,
      score: sr.score || item.score,
      after_score: sr.after_score || item.score,
      company_name: item.company_name,
      file_path: item.file_path,
      missing_keywords: sr.missing_keywords || [],
      section_scores: sr.section_scores || {},
      contact_info: sr.contact_info || {},
      replacements: sr.replacements || [],
      tailored: (sr.replacements || []).length > 0,
    });

    // Switch to Single Scan view if in batch mode
    if (batchMode) setBatchMode(false);

    try {
      const res = await fetch(`http://localhost:8000/api/history/${item.id}/content`);
      if (res.ok) {
        const data = await res.json();
        if (activeRecordRequestRef.current !== item.id) return; // superseded by a newer selection
        if (data.cover_letter) { setCoverLetter(data.cover_letter); setCoverLetterPath(data.cl_path); }
        if (data.mail_draft) { setMailDraft(data.mail_draft); setDraftPath(data.draft_path); }
        if (data.follow_up_draft) { setFollowUpDraft(data.follow_up_draft); }
      }
    } catch { /* ignore */ }

    // Scroll to Post-Production panel
    setTimeout(() => {
      document.getElementById('panel-post-production')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 50);
  };

  const handleHistoryMail = async (id, companyName) => {
    latestMailRequestId.current = id;
    setLoadingMailId(id);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${id}/mail-draft`, { method: 'POST' });
      const data = await res.json();
      if (latestMailRequestId.current !== id) return; // superseded by a newer request
      if (!res.ok) { setError(data.detail || `Error ${res.status}`); return; }
      setHistoryMailModal({ ...data, company_name: companyName, record_id: id });
      setHistoryDraftPath(null);
    } catch {
      if (latestMailRequestId.current === id) setError('Failed to generate mail draft.');
    } finally {
      if (latestMailRequestId.current === id) setLoadingMailId(null);
    }
  };

  const handleSaveHistoryDraft = async () => {
    if (!historyMailModal) return;
    setHistoryDraftSaving(true);
    try {
      const res = await fetch(`http://localhost:8000/api/history/${historyMailModal.record_id}/mail-draft/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: historyMailModal.subject, body: historyMailModal.body }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Save failed'); return; }
      setHistoryDraftPath(data.draft_path);
    } catch {
      setError('Failed to save draft.');
    } finally {
      setHistoryDraftSaving(false);
    }
  };

  const inboxDebounceRef = useRef(null);

  const handleFetchInbox = async (query) => {
    setInboxLoading(true);
    setInboxError(null);
    try {
      const q = query ?? inboxSearch ?? '';
      const res = await fetch(`http://localhost:8000/api/gmail/inbox?q=${encodeURIComponent(q || 'in:inbox')}`);
      const data = await res.json();
      if (res.ok) setInboxMessages(data.messages || []);
      else setInboxError(data.detail || 'Failed to fetch inbox');
    } catch {
      setInboxError('Failed to reach server.');
    } finally {
      setInboxLoading(false);
    }
  };

  const handleInboxSearchChange = (value) => {
    setInboxSearch(value);
    if (inboxDebounceRef.current) clearTimeout(inboxDebounceRef.current);
    inboxDebounceRef.current = setTimeout(() => {
      handleFetchInbox(value);
    }, 800);
  };

  const handleSelectInboxMsg = async (msgId) => {
    setLoadingMsgId(msgId);
    try {
      const res = await fetch(`http://localhost:8000/api/gmail/message/${msgId}`);
      const data = await res.json();
      if (res.ok) {
        setFollowUpEmail(data.body || '');
        setSelectedMsgId(msgId);
        setInboxOpen(false);
      } else {
        setError(data.detail || 'Failed to read message');
      }
    } catch {
      setError('Failed to read message.');
    } finally {
      setLoadingMsgId(null);
    }
  };

  const handleGenerateFollowUp = async () => {
    if (!followUpEmail.trim()) { setError('Paste or select the received email first.'); return; }
    setGeneratingFollowUp(true);
    setError(null);
    try {
      const url = activeRecordId
        ? `http://localhost:8000/api/history/${activeRecordId}/follow-up`
        : 'http://localhost:8000/api/follow-up/standalone';
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ received_email: followUpEmail, instructions: followUpInstructions.trim() || undefined }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || `Error ${res.status}`); return; }
      setFollowUpDraft(data);
      if (data.w2_detected && data.auto_draft_saved) {
        setFollowUpGmailSaved(true);
        setTimeout(() => setFollowUpGmailSaved(false), 8000);
      }
    } catch {
      setError('Failed to generate follow-up.');
    } finally {
      setGeneratingFollowUp(false); fetchUsage();
    }
  };

  const handleSaveFollowUpToGmail = async () => {
    if (!followUpDraft) return;
    setSavingFollowUp(true);
    setFollowUpGmailSaved(false);
    try {
      const res = await fetch('http://localhost:8000/api/gmail/save-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to_emails: followUpDraft.to_emails || [],
          subject: followUpDraft.subject,
          body: followUpDraft.body,
          record_id: activeRecordId,
          attach_resume: fuAttach.resume,
          attach_cover_letter: fuAttach.cover_letter,
          attach_dl: fuAttach.dl,
          attach_gc: fuAttach.gc,
        }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Failed to save to Gmail'); return; }
      setFollowUpGmailSaved(true);
      setTimeout(() => setFollowUpGmailSaved(false), 5000);
    } catch {
      setError('Failed to save follow-up to Gmail.');
    } finally {
      setSavingFollowUp(false);
    }
  };

  const scoreAccent = (score) => {
    if (score >= 85) return '#2ebd73';
    if (score >= 60) return '#c89b3c';
    return '#d94f4f';
  };

  const deltaScore = result?.after_score != null ? result.after_score - result.score : 0;

  const sidebarNav = (activePage) => (
    <nav style={sidebarStyles.nav}>
      <div style={sidebarStyles.navBrand}>Job Tailored Resume</div>
      <ul style={sidebarStyles.navList}>
        <li>
          <button
            style={activePage === 'command-center' ? sidebarStyles.navItemActive : sidebarStyles.navItem}
            onClick={() => setCurrentPage('command-center')}
          >
            Command Center
          </button>
        </li>
        <li>
          <button
            style={activePage === 'dashboard' ? sidebarStyles.navItemActive : sidebarStyles.navItem}
            onClick={() => setCurrentPage('dashboard')}
          >
            Resume Tailor
          </button>
        </li>
        <li>
          <button
            style={activePage === 'job-matcher' ? sidebarStyles.navItemActive : sidebarStyles.navItem}
            onClick={() => setCurrentPage('job-matcher')}
          >
            Job Finder
          </button>
        </li>
        <li>
          <button
            style={activePage === 'search' ? sidebarStyles.navItemActive : sidebarStyles.navItem}
            onClick={() => setCurrentPage('search')}
          >
            Search
          </button>
        </li>
        <li>
          <button
            style={activePage === 'inbox' ? sidebarStyles.navItemActive : sidebarStyles.navItem}
            onClick={() => setCurrentPage('inbox')}
          >
            Inbox
          </button>
        </li>
        <li>
          <button
            style={activePage === 'info' ? sidebarStyles.navItemActive : sidebarStyles.navItem}
            onClick={() => setCurrentPage('info')}
          >
            Info
          </button>
        </li>
        <li>
          <button
            style={activePage === 'exp' ? sidebarStyles.navItemActive : sidebarStyles.navItem}
            onClick={() => setCurrentPage('exp')}
          >
            Exp
          </button>
        </li>
      </ul>
    </nav>
  );


  // Show Command Center
  if (currentPage === 'command-center') {
    return (
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        {sidebarNav('command-center')}
        <div style={{ flex: 1, overflow: 'auto', background: 'var(--ink)' }}>
          <CommandCenter
            onSendToTailor={(jd) => { setJdText(jd); setCurrentPage('dashboard'); }}
            onSaveToApplications={handleSaveToApplications}
            onViewAllMatches={() => setCurrentPage('job-matches')}
            selectedResumeName={selectedResumeName}
            onChangeResume={() => setCurrentPage('dashboard')}
            initialJobId={pendingCommandCenterJobId}
            onConsumeInitialJobId={() => setPendingCommandCenterJobId(null)}
          />
        </div>
      </div>
    );
  }

  // Show All Job Matches (drill-down from Command Center)
  if (currentPage === 'job-matches') {
    return (
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        {sidebarNav('command-center')}
        <div style={{ flex: 1, overflow: 'auto', background: 'var(--ink)' }}>
          <JobMatches
            onBack={() => setCurrentPage('command-center')}
            onSendToTailor={(jd) => { setJdText(jd); setCurrentPage('dashboard'); }}
            onSaveToApplications={handleSaveToApplications}
            selectedResumeName={selectedResumeName}
          />
        </div>
      </div>
    );
  }

  if (currentPage === 'inbox') {
    return (
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        {sidebarNav('inbox')}
        <div style={{ flex: 1, overflow: 'auto', background: 'var(--ink)' }}>
          <InboxPage
            gmailConnected={gmailConnected}
            gmailEmail={gmailEmail}
            gmailCanOrganize={gmailCanOrganize}
            onRefreshStatus={checkGmailStatus}
            onDisconnect={handleDisconnectGmail}
            onOpenJob={(jobId) => { setPendingCommandCenterJobId(jobId); setCurrentPage('command-center'); }}
          />
        </div>
      </div>
    );
  }
  // Show SearchPage
  if (currentPage === 'search') {
    return (
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        {sidebarNav('search')}
        <div style={{ flex: 1, overflow: 'auto' }}>
          <SearchPage onSelectRecord={(r) => {
            const item = { id: r.id, company_name: r.company_name, score: r.score, status: r.status, scan_result: {} };
            handleSelectRecord(item);
            setCurrentPage('dashboard');
          }} />
        </div>
      </div>
    );
  }

    // Show JobMatcher if on job-matcher page
  if (currentPage === 'job-matcher') {
    return (
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        {sidebarNav('job-matcher')}
        <div style={{ flex: 1, overflow: 'auto' }}>
          <JobMatcher onApply={(jd) => { setJdText(jd); setCurrentPage('dashboard'); }} />
        </div>
      </div>
    );
  }

  // Show Info page
  if (currentPage === 'exp') {
    const q = expSearchQuery.toLowerCase();
    const filteredExperience = TECH_EXPERIENCE.filter(item =>
      (expCategoryFilter === 'All' || item.category === expCategoryFilter) &&
      item.name.toLowerCase().includes(q)
    );
    const ratingTier = (rating) => {
      const n = parseFloat(rating);
      if (Number.isNaN(n)) return 'none';
      if (n >= 9) return 'high';
      if (n >= 8) return 'mid';
      return 'low';
    };
    const toggleExpanded = (name) => {
      setExpExpanded(prev => {
        const next = new Set(prev);
        next.has(name) ? next.delete(name) : next.add(name);
        return next;
      });
    };

    return (
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        {sidebarNav('exp')}
        <div style={{ flex: 1, overflow: 'auto' }}>
          <div className="app">
            <div className="grain" aria-hidden="true" />
            <main className="main-content">
              <div className="exp-page">
                <div className="exp-header">
                  <h2 className="exp-title">Technology Experience</h2>
                  <span className="exp-count">{filteredExperience.length} of {TECH_EXPERIENCE.length}</span>
                </div>

                <input
                  type="text"
                  className="exp-search"
                  placeholder="Search technology…"
                  value={expSearchQuery}
                  onChange={(e) => setExpSearchQuery(e.target.value)}
                  autoFocus
                />

                <div className="exp-pills">
                  <button
                    className={`exp-pill${expCategoryFilter === 'All' ? ' active' : ''}`}
                    onClick={() => setExpCategoryFilter('All')}
                  >
                    All
                  </button>
                  {TECH_CATEGORIES.map(cat => (
                    <button
                      key={cat}
                      className={`exp-pill${expCategoryFilter === cat ? ' active' : ''}`}
                      onClick={() => setExpCategoryFilter(cat === expCategoryFilter ? 'All' : cat)}
                    >
                      {cat}
                    </button>
                  ))}
                </div>

                <div className="exp-table-wrap">
                  <table className="exp-table">
                    <thead>
                      <tr>
                        <th className="exp-th-toggle"></th>
                        <th>Technology</th>
                        <th>Category</th>
                        <th>Experience</th>
                        <th>Rating</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredExperience.map(item => {
                        const isOpen = expExpanded.has(item.name);
                        return (
                        <React.Fragment key={item.name}>
                          <tr
                            className={`exp-row${isOpen ? ' exp-row-open' : ''}`}
                            onClick={() => toggleExpanded(item.name)}
                          >
                            <td className="exp-toggle-cell">
                              <span className={`exp-chevron${isOpen ? ' open' : ''}`}>▸</span>
                            </td>
                            <td className="exp-name">{item.name}</td>
                            <td><span className="exp-cat-tag">{item.category}</span></td>
                            <td className="exp-years">{item.years}</td>
                            <td><span className={`exp-rating exp-rating-${ratingTier(item.rating)}`}>{item.rating}</span></td>
                          </tr>
                          {isOpen && (
                            <tr className="exp-detail-row">
                              <td colSpan={5}>
                                <div className="exp-detail">
                                  <div className="exp-detail-block">
                                    <span className="exp-detail-label">What it&rsquo;s used for</span>
                                    <p className="exp-detail-text">{item.info.use}</p>
                                  </div>
                                  <div className="exp-detail-block">
                                    <span className="exp-detail-label">How it works</span>
                                    <p className="exp-detail-text">{item.info.how}</p>
                                  </div>
                                  <div className="exp-detail-block">
                                    <span className="exp-detail-label">Where we used it</span>
                                    <p className="exp-detail-text">{item.info.where}</p>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                  {filteredExperience.length === 0 && <p className="empty-log">No technology matches your search.</p>}
                </div>
              </div>
            </main>
          </div>
        </div>
      </div>
    );
  }

  if (currentPage === 'info') {
    const filteredAddresses = infoAddresses.filter(item => {
      const q = addressSearchQuery.toLowerCase();
      return (item.company_name || '').toLowerCase().includes(q) ||
             (item.user_address || '').toLowerCase().includes(q) ||
             (item.phone || '').toLowerCase().includes(q) ||
             (item.name || '').toLowerCase().includes(q) ||
             (item.email || '').toLowerCase().includes(q);
    });

    return (
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        {sidebarNav('info')}
        <div style={{ flex: 1, overflow: 'auto' }}>
          <div className="app">
            <div className="grain" aria-hidden="true" />
            <main className="main-content">
              {/* Employer Details */}
              <div className="panel panel-enter">
                <div className="panel-tag">
                  <span className="panel-num">01</span>
                  <span className="panel-title">Employer Details</span>
                </div>
                <div className="info-contact-card">
                  <div className="info-contact-row">
                    <span className="info-contact-key">Email</span>
                    <span className="info-contact-value">suneendra@coreit-tech.com</span>
                  </div>
                  <div className="info-contact-row">
                    <span className="info-contact-key">Tel</span>
                    <span className="info-contact-value">14694441962 ext : 8406</span>
                  </div>
                </div>
                <div className="info-contact-card" style={{ marginTop: '0.75rem' }}>
                  <div className="info-contact-row">
                    <span className="info-contact-key">Email</span>
                    <span className="info-contact-value">ushasri@coreit-tech.com</span>
                  </div>
                  <div className="info-contact-row">
                    <span className="info-contact-key">Tel</span>
                    <span className="info-contact-value">14694447419 ext : 8408</span>
                  </div>
                </div>
              </div>

              {/* Telegram Integration */}
              <div className="panel panel-enter" style={{ animationDelay: '60ms' }}>
                <div className="panel-tag">
                  <span className="panel-num">02</span>
                  <span className="panel-title">Telegram Bot</span>
                  {telegramStatus?.polling && <span className="panel-active-co">Live</span>}
                </div>
                {telegramStatus?.configured ? (
                  <div className="info-whatsapp-connected">
                    <div className="info-whatsapp-status">
                      <span className="info-whatsapp-dot">{telegramStatus.polling ? '●' : '○'}</span>
                      {telegramStatus.polling ? 'Bot is running and listening for messages' : 'Bot configured but not polling — restart backend'}
                    </div>
                    {telegramStatus.bot_username && (
                      <div className="info-contact-card">
                        <div className="info-contact-row">
                          <span className="info-contact-key">Bot</span>
                          <span className="info-contact-value">@{telegramStatus.bot_username}</span>
                        </div>
                      </div>
                    )}
                    <div className="info-whatsapp-instructions">
                      <div className="info-whatsapp-step">1. Open Telegram and search for @{telegramStatus.bot_username || 'your_bot'}</div>
                      <div className="info-whatsapp-step">2. Send /start to begin</div>
                      <div className="info-whatsapp-step">3. Paste a Job Description and send it</div>
                      <div className="info-whatsapp-step">4. The bot processes it and replies with the score and status</div>
                    </div>
                  </div>
                ) : (
                  <div className="info-whatsapp-setup">
                    <p className="panel-placeholder">Telegram bot is not configured yet.</p>
                    <div className="info-whatsapp-instructions">
                      <div className="info-whatsapp-step">1. Open Telegram and message @BotFather</div>
                      <div className="info-whatsapp-step">2. Send /newbot and follow the prompts</div>
                      <div className="info-whatsapp-step">3. Copy the bot token</div>
                      <div className="info-whatsapp-step">4. Add TELEGRAM_BOT_TOKEN to your .env file</div>
                    </div>
                  </div>
                )}
              </div>

              {/* Saved Addresses */}
              <div className="panel panel-wide panel-enter" style={{ animationDelay: '120ms' }}>
                <div className="panel-top-row">
                  <div className="panel-tag inline">
                    <span className="panel-num">03</span>
                    <span className="panel-title">Saved Addresses</span>
                  </div>
                  <span className="history-count">{filteredAddresses.length} address{filteredAddresses.length !== 1 ? 'es' : ''}</span>
                </div>
                <input
                  type="text"
                  className="history-search"
                  placeholder="Search addresses…"
                  value={addressSearchQuery}
                  onChange={(e) => setAddressSearchQuery(e.target.value)}
                  style={{ marginBottom: '1.5rem', maxWidth: '100%' }}
                />
                <div className="info-address-list">
                  {filteredAddresses.map((item, index) => {
                    const contactDisplay = item.phone || item.name;
                    return (
                    <div key={item.id || index} className="info-address-card">
                      <div className="info-address-company">{item.company_name}</div>
                      <div className="info-address-text">{item.user_address}</div>
                      {(contactDisplay || item.email) && (
                        <div className="info-address-contact">
                          {contactDisplay && <div className="info-address-field"><span className="info-address-label">Contact</span>{contactDisplay}</div>}
                          {item.email && <div className="info-address-field"><span className="info-address-label">Email</span>{item.email}</div>}
                        </div>
                      )}
                    </div>
                  )})}
                  {infoAddresses.length === 0 && <p className="empty-log">No addresses saved yet.</p>}
                  {infoAddresses.length > 0 && filteredAddresses.length === 0 && <p className="empty-log">No addresses match your search.</p>}
                </div>
              </div>
            </main>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex' }}>
      {sidebarNav('dashboard')}
      {/* Main App */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        <div className="app">
          <div className="grain" aria-hidden="true" />

          <header className="site-header">
        <div className="header-inner">
          <div className="brand">
            <FilmIcon />
            <h1>TRAILERD</h1>
          </div>
          <p className="site-tagline">AI Resume Tailoring Studio<br />Frame your story. Land the role.</p>
        </div>
        <div className="header-rule" />
      </header>

      <main className="main-content">
        <div className="mode-tabs">
          <button className={`mode-tab${!batchMode ? ' active' : ''}`} onClick={() => { setBatchMode(false); setError(null); }}>Single Scan</button>
          <button className={`mode-tab${batchMode ? ' active' : ''}`} onClick={() => { setBatchMode(true); setError(null); }}>⚡ Batch Mode</button>
          <button className={`mode-tab usage-tab${usageOpen ? ' active' : ''}`} onClick={() => { setUsageOpen(u => !u); fetchUsage(); }}>
            $ Usage {usageStats ? `($${usageStats.all_time?.cost?.toFixed(2) || '0.00'})` : ''}
          </button>
        </div>

        {usageOpen && usageStats && (
          <div className="usage-dashboard">
            <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '0.75rem' }}>
              Gemini/Claude costs below are estimates based on published per-token rates, not billing-account data — actual charges may differ slightly.
            </div>
            <div className="usage-cards">
              <div className="usage-card">
                <div className="usage-card-label">Today</div>
                <div className="usage-card-cost">${usageStats.today?.cost?.toFixed(4) || '0.0000'}</div>
                <div className="usage-card-calls">{usageStats.today?.calls || 0} calls</div>
              </div>
              <div className="usage-card">
                <div className="usage-card-label">This Week</div>
                <div className="usage-card-cost">${usageStats.week?.cost?.toFixed(4) || '0.0000'}</div>
                <div className="usage-card-calls">{usageStats.week?.calls || 0} calls</div>
              </div>
              <div className="usage-card">
                <div className="usage-card-label">This Month</div>
                <div className="usage-card-cost">${usageStats.month?.cost?.toFixed(4) || '0.0000'}</div>
                <div className="usage-card-calls">{usageStats.month?.calls || 0} calls</div>
              </div>
              <div className="usage-card">
                <div className="usage-card-label">All Time</div>
                <div className="usage-card-cost">${usageStats.all_time?.cost?.toFixed(4) || '0.0000'}</div>
                <div className="usage-card-calls">{usageStats.all_time?.calls || 0} calls</div>
              </div>
            </div>
            {usageStats.all_time?.by_model && (
              <div className="usage-breakdown">
                <div className="usage-breakdown-title">By Model</div>
                <div className="usage-breakdown-rows">
                  {Object.entries(usageStats.all_time.by_model).map(([model, info]) => (
                    <div key={model} className="usage-row">
                      <span className="usage-row-model">{model}</span>
                      <span className="usage-row-calls">{info.calls} calls</span>
                      <span className="usage-row-cost">${info.cost?.toFixed(4)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {usageStats.jsearch_quota && (
              <div className="usage-breakdown">
                <div className="usage-breakdown-title">JSearch Free Tier</div>
                <div className="jsearch-quota">
                  <div className="jsearch-quota-bar">
                    <div
                      className="jsearch-quota-fill"
                      style={{ width: `${Math.min(100, (usageStats.jsearch_quota.used / usageStats.jsearch_quota.limit) * 100)}%` }}
                    />
                  </div>
                  <div className="jsearch-quota-label">
                    {usageStats.jsearch_quota.used} / {usageStats.jsearch_quota.limit} free searches used this month
                    <span className="jsearch-quota-remaining"> ({usageStats.jsearch_quota.remaining} left)</span>
                  </div>
                </div>
              </div>
            )}
            {usageStats.all_time?.by_operation && (
              <div className="usage-breakdown">
                <div className="usage-breakdown-title">By Operation</div>
                <div className="usage-breakdown-rows">
                  {Object.entries(usageStats.all_time.by_operation).map(([op, count]) => (
                    <div key={op} className="usage-row">
                      <span className="usage-row-model">{op.replace(/_/g, ' ')}</span>
                      <span className="usage-row-calls">{count} calls</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {usageStats.daily_breakdown && Object.keys(usageStats.daily_breakdown).length > 0 && (
              <div className="usage-breakdown">
                <div className="usage-breakdown-title">Daily (Last 7 Days)</div>
                <div className="usage-breakdown-rows">
                  {Object.entries(usageStats.daily_breakdown).sort((a, b) => b[0].localeCompare(a[0])).map(([day, info]) => (
                    <div key={day} className="usage-row">
                      <span className="usage-row-model">{day}</span>
                      <span className="usage-row-calls">{info.calls} calls</span>
                      <span className="usage-row-cost">${info.cost?.toFixed(4)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="usage-projected">
              Projected monthly: <strong>${usageStats.projected_monthly?.toFixed(2) || '0.00'}</strong> (based on today's usage)
            </div>
          </div>
        )}

        <div className="workspace" style={{ display: batchMode ? 'none' : 'grid' }}>

          {/* ── Left: Input Panel ── */}
          <div id="panel-pre-production" className="panel panel-enter" style={{ animationDelay: '0ms' }}>
            <div className="panel-tag">
              <span className="panel-num">01</span>
              <span className="panel-title">Pre-Production</span>
            </div>

            {rerunRecordId && (
              <div className="status-banner status-original" style={{ marginBottom: '0.75rem' }}>
                ⟳ Re-running scan for <strong>{rerunCompanyName}</strong> — this will update the existing tailored resume, not create a new entry.
                <button className="rerun-cancel-btn" onClick={() => { setRerunRecordId(null); setRerunCompanyName(null); }}>Cancel</button>
              </div>
            )}

            {error && <div className="error-banner">⚠ {error}</div>}

            {duplicateConflict && (
              <div className="error-banner duplicate-conflict-banner">
                <button className="dup-rerun-btn" onClick={handleAcceptDuplicateRerun}>⟳ Re-run &amp; Update This Entry</button>
                <button className="dup-dismiss-btn" onClick={() => { setDuplicateConflict(null); setError(null); }}>Dismiss</button>
              </div>
            )}

            {experienceConflict && (
              <div className="error-banner duplicate-conflict-banner">
                <button className="dup-rerun-btn" onClick={handleAcceptExperienceOverride}>No Problem, Continue</button>
                <button className="dup-dismiss-btn" onClick={() => { setExperienceConflict(null); setError(null); }}>Cancel</button>
              </div>
            )}

            <div className="field">
              <label className="field-label">AI Notes <span style={{ fontWeight: 400, opacity: 0.5 }}>(optional)</span></label>
              <textarea
                className="field-textarea ai-notes-textarea"
                placeholder="e.g. Keep ATS score 100, focus on Kubernetes experience, emphasize CI/CD pipelines…"
                value={aiNotes}
                onChange={e => setAiNotes(e.target.value)}
                rows={2}
              />
            </div>

            <div className="field">
              <label className="field-label">Job Description</label>
              <div className="textarea-wrap">
                <textarea
                  className="field-textarea"
                  placeholder="Paste the job description here… (Ctrl+Enter to scan)"
                  value={jdText}
                  onChange={e => setJdText(e.target.value)}
                  onKeyDown={e => { if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); handleScan(); } }}
                />
                {jdText.length > 0 && <span className="char-count">{jdText.length} chars</span>}
              </div>
            </div>

            <div className="field">
              <label className="field-label">Base Resume</label>
              <div
                className={`resume-manager${dragging ? ' dragging' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f) handleAddResume(f); }}
              >
                {storedResumes.length === 0 && !uploadingResume && (
                  <p className="resume-empty">No resumes yet — add one below or drag a .docx here</p>
                )}
                {storedResumes.map(r => (
                  <div key={r.filename} className={`resume-item${selectedResumeName === r.filename ? ' selected' : ''}`} onClick={() => handleResumeSelect(r.filename)}>
                    <span className="resume-item-dot">{selectedResumeName === r.filename ? '●' : '○'}</span>
                    <span className="resume-item-name" title={r.filename}>{r.filename.replace(/\.docx$/i, '')}</span>
                    <button className="resume-item-del" onClick={e => { e.stopPropagation(); handleResumeDelete(r.filename); }} title="Remove">×</button>
                  </div>
                ))}
                {uploadingResume && (
                  <div className="resume-item">
                    <span className="resume-item-dot spin-icon" style={{ color: 'var(--gold)' }}>▶</span>
                    <span className="resume-item-name">Uploading…</span>
                  </div>
                )}
                <label className="resume-add-btn">
                  + Add Resume (.docx)
                  <input type="file" accept=".docx" onChange={e => { handleAddResume(e.target.files?.[0]); e.target.value = ''; }} />
                </label>
              </div>
            </div>

            <div className="field">
              <button className="profile-toggle" onClick={() => setProfileOpen(p => !p)}>
                {profileOpen ? '▾' : '▸'} Personal Profile {profileLoaded ? <span className="profile-badge" title="Profile saved and active">● Active</span> : <span className="profile-badge-empty" title="No profile yet — add your details">○ Not set</span>}
              </button>
              {profileOpen && (
                <div className="profile-editor">
                  <div className="profile-hint">Upload personal docs (DL, GC, etc.) to auto-extract key facts, or type them manually. Raw files are never stored — only the extracted facts are saved.</div>
                  <div className="profile-upload-row">
                    <label className="profile-upload-btn">
                      {profileUploading ? '⏳ Extracting…' : '📄 Upload Document'}
                      <input type="file" accept=".pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp" onChange={handleProfileUpload} disabled={profileUploading} hidden />
                    </label>
                    <span className="profile-upload-hint">PDF, DOCX, or Image</span>
                  </div>
                  {profileUploadMsg && <div className="profile-upload-msg">{profileUploadMsg}</div>}
                  <textarea
                    className="field-textarea profile-textarea"
                    placeholder={"Work Authorization: US Green Card holder\nLocation: Open to relocation\nAvailability: Immediate\nNotice Period: None\nWilling to Travel: Yes\nPreferred Work Mode: Hybrid or Remote"}
                    value={profileText}
                    onChange={e => setProfileText(e.target.value)}
                    rows={6}
                  />
                  <button className="profile-save-btn" onClick={handleSaveProfile} disabled={profileSaving}>
                    {profileSaving ? '…' : '💾 Save Profile'}
                  </button>
                </div>
              )}
            </div>

            <div className="btn-row">
              <button className={`action-btn${loading ? ' loading' : ''}`} onClick={() => handleScan()} disabled={loading} style={{ flex: 2 }}>
                {loading
                  ? <span className="btn-loading"><span className="spin-icon">▶</span> {rerunRecordId ? 'Re-running…' : 'Processing…'}</span>
                  : rerunRecordId ? '⟳ RE-RUN' : '▶ ACTION'}
              </button>
              {(result || jdText) && (
                <button className="action-btn reset-btn" onClick={handleReset} disabled={loading} style={{ flex: 1 }}>Reset</button>
              )}
            </div>
          </div>

          {/* ── Right: Results Panel ── */}
          <div id="panel-post-production" className="panel panel-enter" style={{ animationDelay: '80ms' }}>
            <div className="panel-tag">
              <span className="panel-num">02</span>
              <span className="panel-title">Post-Production</span>
            </div>

            {loading ? (
              <div className="scanning">
                <div className="scan-line" />
                <EmptyResultsIcon />
                <p className="scan-label">Analyzing resume…</p>
              </div>
            ) : result ? (
              <div className="results">
                <div className="company-badge">
                  <span className="company-label">Company</span>
                  <span className="company-name">{result.company_name}</span>
                </div>

                <div className="score-row">
                  <ScoreRing key={`before-${result.score}`} score={result.score} label="Original" accent={scoreAccent(result.score)} />
                  {result.after_score != null && result.after_score !== result.score && (
                    <>
                      <div className="score-arrow">→</div>
                      <ScoreRing key={`after-${result.after_score}`} score={result.after_score} label="Tailored" accent={scoreAccent(result.after_score)} />
                    </>
                  )}
                </div>

                <div className={`status-banner ${result.tailored ? 'status-tailored' : 'status-original'}`}>
                  {result.tailored && deltaScore > 0
                    ? `↑ +${deltaScore} pts — resume automatically tailored`
                    : result.tailored ? 'Resume tailored for this role'
                    : result.score >= 85 ? `Score ${result.score}% — no tailoring needed`
                    : 'Score strong — no tailoring needed'}
                </div>

                {result.file_path && (
                  <div className="result-downloads">
                    <a href={`http://localhost:8000/api/download/${result.file_path.replace(/^trailerd\//, '')}`} className="download-btn" download>
                      ↓ {result.tailored ? 'Download Tailored Resume' : 'Download Resume'}
                    </a>
                    {result.pdf_path && (
                      <a href={`http://localhost:8000/api/download/${result.pdf_path.replace(/^trailerd\//, '')}`} className="download-btn" download>
                        ↓ Download PDF
                      </a>
                    )}
                    <div className="file-dl-row">
                      <a href={`http://localhost:8000/api/download/${result.file_path.replace(/[^/]+\.docx$/, 'jd_info.txt').replace(/^trailerd\//, '')}`} className="file-dl-link" download>
                        ↓ jd_info.txt
                      </a>
                    </div>
                  </div>
                )}

                {result.contact_info && Object.values(result.contact_info).some(v => v) && (
                  <div className="contact-info-strip">
                    <div className="contact-info-label">Vendor / Recruiter Contact</div>
                    <div className="contact-info-fields">
                      {result.contact_info.name && <span className="contact-field"><span className="contact-key">Name</span>{result.contact_info.name}</span>}
                      {result.contact_info.email && <span className="contact-field"><span className="contact-key">Email</span>{result.contact_info.email}</span>}
                      {result.contact_info.phone && <span className="contact-field"><span className="contact-key">Phone</span>{result.contact_info.phone}</span>}
                    </div>
                  </div>
                )}

                {result.missing_keywords?.length > 0 && (
                  <div className="keyword-gap">
                    <div className="keyword-gap-header">Missing Keywords</div>
                    <div className="keyword-chips">
                      {result.missing_keywords.map((kw, idx) => <span key={idx} className="keyword-chip">{kw}</span>)}
                    </div>
                  </div>
                )}

                {result.section_scores && Object.keys(result.section_scores).length > 0 && (
                  <div className="section-breakdown">
                    <div className="section-breakdown-header">Section Breakdown</div>
                    <div className="section-bars">
                      {Object.entries(result.section_scores).map(([section, sectionScore]) => (
                        <div key={section} className="section-bar-row">
                          <div className="section-bar-label">{section}</div>
                          <div className="section-bar-track">
                            <div className="section-bar-fill" style={{ width: `${sectionScore}%`, background: sectionScore >= 85 ? 'var(--success)' : sectionScore >= 60 ? 'var(--gold)' : 'var(--danger)' }} />
                          </div>
                          <div className="section-bar-value" style={{ color: sectionScore >= 85 ? 'var(--success)' : sectionScore >= 60 ? 'var(--gold)' : 'var(--danger)' }}>{sectionScore}%</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {result.replacements?.length > 0 && (
                  <div className="diff-section">
                    <div className="diff-header">AI Changes — {result.replacements.length} edit{result.replacements.length !== 1 ? 's' : ''} {result.replacements.length > 1 && <span className="diff-scroll-hint">↕ scroll for more</span>}</div>
                    <div className="diff-list">
                      {result.replacements.map((rep, idx) => (
                        <div key={idx} className="diff-item">
                          <div className="diff-removed">− {rep.original}</div>
                          <div className="diff-added">+ {rep.new}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="diff-section add-points-section">
                  <div className="diff-header">Add More Points <span className="field-label-optional">(optional)</span></div>
                  <div className="add-points-body">
                    <label className="field-label">Point(s) to add</label>
                    <textarea
                      className="field-textarea add-points-textarea"
                      placeholder="e.g. Led migration of legacy VMs to EKS, cutting infra costs by 30%"
                      value={addPointsText}
                      onChange={e => setAddPointsText(e.target.value)}
                      rows={3}
                    />
                    <label className="field-label" style={{ marginTop: '0.7rem' }}>
                      Add under this project/company <span className="field-label-optional">(optional)</span>
                    </label>
                    <input
                      type="text"
                      className="add-points-target-input"
                      placeholder="e.g. Acme Corp, or leave blank to let AI decide"
                      value={addPointsTarget}
                      onChange={e => setAddPointsTarget(e.target.value)}
                    />
                    <button
                      className="action-btn"
                      onClick={handleAddPoints}
                      disabled={addPointsLoading || !addPointsText.trim() || !activeRecordId}
                      style={{ marginTop: '0.7rem' }}
                    >
                      {addPointsLoading ? <span className="btn-loading"><span className="spin-icon">▶</span> Adding…</span> : '+ Add to Tailored Resume'}
                    </button>
                    {addPointsSuccess && <div className="status-banner status-tailored" style={{ marginTop: '0.6rem' }}>{addPointsSuccess}</div>}
                  </div>
                </div>
              </div>
            ) : (
              <div className="results-empty">
                <div className="empty-icon"><EmptyResultsIcon /></div>
                <p className="empty-label">Fill in Pre-Production<br />and hit ACTION to begin</p>
              </div>
            )}
          </div>
        </div>

        {/* ── Cover Letter & Email Draft ── */}
        <div className="workspace" id="panels-cl-mail">
            {/* Panel 03 — Cover Letter */}
            <div className="panel panel-enter" style={{ animationDelay: '60ms' }}>
              <div className="panel-tag">
                <span className="panel-num">03</span>
                <span className="panel-title">Cover Letter</span>
                {activeCompanyName && <span className="panel-active-co">{activeCompanyName}</span>}
              </div>
              {!activeRecordId ? (
                <p className="panel-placeholder">Run a scan or click a company name in the Production Log.</p>
              ) : !coverLetter ? (
                <button className="action-btn" onClick={handleGenerateCL} disabled={generatingCL} style={{ marginTop: 0 }}>
                  {generatingCL ? <span className="btn-loading"><span className="spin-icon">▶</span> Generating…</span> : '▶ Generate Cover Letter'}
                </button>
              ) : (
                <div className="cover-letter-section">
                  <div className="cl-text">{coverLetter}</div>
                  <div className="cl-actions">
                    <button className="cl-copy-btn" onClick={() => { navigator.clipboard.writeText(coverLetter); setCopied(true); setTimeout(() => setCopied(false), 2000); }}>
                      {copied ? '✓ Copied' : '↑ Copy'}
                    </button>
                    {coverLetterPath && (
                      <a href={`http://localhost:8000/api/download/${coverLetterPath.replace(/^trailerd\//, '')}`} className="cl-download-btn" download>↓ Download .docx</a>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Panel 04 — Email Draft */}
            <div className="panel panel-enter" style={{ animationDelay: '100ms' }}>
              <div className="panel-tag">
                <span className="panel-num">04</span>
                <span className="panel-title">Email Draft</span>
                <span className="mail-ollama-badge" style={{ marginLeft: '0.5rem' }}>via OpenAI</span>
                {activeCompanyName && <span className="panel-active-co">{activeCompanyName}</span>}
              </div>
              {!activeRecordId ? (
                <p className="panel-placeholder">Run a scan or click a company name in the Production Log.</p>
              ) : !mailDraft ? (
                <button className="action-btn" onClick={handleGenerateMail} disabled={generatingMail} style={{ marginTop: 0 }}>
                  {generatingMail ? <span className="btn-loading"><span className="spin-icon">▶</span> Generating…</span> : '✉ Generate Email Draft'}
                </button>
              ) : (
                <div className="mail-draft-section">
                  <div className="mail-draft-body">
                    {mailDraft.to_emails?.length > 0 && (
                      <div className="mail-field">
                        <span className="mail-field-label">To</span>
                        <div className="mail-to-chips">
                          {mailDraft.to_emails.map((email, i) => <span key={i} className="mail-to-chip">{email}</span>)}
                        </div>
                      </div>
                    )}
                    <div className="mail-field">
                      <div className="mail-subject-row">
                        <span className="mail-field-label">Subject</span>
                        <button className="mail-copy-small" onClick={() => { navigator.clipboard.writeText(mailDraft.subject); setCopiedField('subject'); setTimeout(() => setCopiedField(null), 2000); }}>
                          {copiedField === 'subject' ? '✓' : '↑ Copy'}
                        </button>
                      </div>
                      <div className="mail-subject-text">{mailDraft.subject}</div>
                    </div>
                    <div className="mail-field">
                      <span className="mail-field-label">Body</span>
                      <div className="mail-body-text">{mailDraft.body}</div>
                    </div>
                  </div>
                  <div className="mail-draft-actions">
                    <button className="mail-act-btn" onClick={() => {
                      const full = `To: ${(mailDraft.to_emails || []).join(', ')}\nSubject: ${mailDraft.subject}\n\n${mailDraft.body}`;
                      navigator.clipboard.writeText(full); setCopiedField('all'); setTimeout(() => setCopiedField(null), 2000);
                    }}>
                      {copiedField === 'all' ? '✓ Copied All' : '↑ Copy All'}
                    </button>
                    {mailDraft.to_emails?.length > 0 && (
                      <a
                        href={`mailto:${mailDraft.to_emails.join(',')}?subject=${encodeURIComponent(mailDraft.subject)}&body=${encodeURIComponent(mailDraft.body)}`}
                        className="mail-act-btn mail-mailto-btn"
                      >
                        ✉ Open in Mail App
                      </a>
                    )}
                    {!draftPath ? (
                      <button className="mail-act-btn mail-save-btn" onClick={handleSaveDraft} disabled={savingDraft}>
                        {savingDraft ? '…' : '💾 Save to Folder'}
                      </button>
                    ) : (
                      <a href={`http://localhost:8000/api/download/${draftPath.replace(/^trailerd\//, '')}`} className="mail-act-btn mail-dl-btn" download>
                        ↓ Download .txt
                      </a>
                    )}
                    {gmailConnected ? (
                      <button className="mail-act-btn mail-gmail-btn" onClick={handleSaveToGmail} disabled={savingToGmail}>
                        {savingToGmail ? '…' : gmailSaved ? '✓ Saved to Gmail' : '✉ Save to Gmail Drafts'}
                      </button>
                    ) : (
                      <a href="http://localhost:8000/api/gmail/auth" className="mail-act-btn mail-gmail-connect-btn">
                        ✉ Connect Gmail
                      </a>
                    )}
                  </div>
                  {gmailConnected && (
                    <div className="gmail-status">
                      <span className="gmail-status-dot">●</span> Connected: {gmailEmail}
                      <button className="gmail-disconnect-btn" onClick={handleDisconnectGmail}>Disconnect</button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

        {/* ── Follow-Up Mail ── */}
        <div className="panel panel-wide panel-enter" style={{ animationDelay: '140ms' }}>
          <div className="panel-tag">
            <span className="panel-num">05</span>
            <span className="panel-title">Follow-Up</span>
            <span className="mail-ollama-badge" style={{ marginLeft: '0.5rem' }}>via OpenAI</span>
            {activeCompanyName && <span className="panel-active-co">{activeCompanyName}</span>}
          </div>
            <div className="follow-up-section">
              <div className="follow-up-input">
                <label className="field-label">Received Email</label>
                {gmailConnected && (
                  <div className="inbox-picker">
                    <button className="inbox-toggle-btn" onClick={() => { if (!inboxOpen) { handleFetchInbox(''); } setInboxOpen(o => !o); }}>
                      {inboxOpen ? '▾ Hide Inbox' : '▸ Select from Gmail'}
                    </button>
                    {inboxOpen && (
                      <div className="inbox-dropdown">
                        <div className="inbox-search-row">
                          <input
                            type="text"
                            className="inbox-search-input"
                            placeholder="Search by name, email, company…"
                            value={inboxSearch}
                            onChange={e => handleInboxSearchChange(e.target.value)}
                            autoFocus
                          />
                          {inboxLoading && <span className="inbox-search-btn" style={{ pointerEvents: 'none' }}>…</span>}
                        </div>
                        {inboxError && <p className="inbox-empty inbox-error">{inboxError}</p>}
                        {!inboxError && inboxMessages.length === 0 && !inboxLoading && <p className="inbox-empty">No messages found</p>}
                        <div className="inbox-list">
                          {inboxMessages.map(msg => (
                            <button
                              key={msg.id}
                              className={`inbox-msg${selectedMsgId === msg.id ? ' selected' : ''}`}
                              onClick={() => handleSelectInboxMsg(msg.id)}
                              disabled={loadingMsgId === msg.id}
                            >
                              <span className="inbox-msg-from">{msg.from?.replace(/<.*>/, '').trim() || 'Unknown'}</span>
                              <span className="inbox-msg-subject">{msg.subject || '(no subject)'}</span>
                              <span className="inbox-msg-snippet">{msg.snippet}</span>
                              {loadingMsgId === msg.id && <span className="inbox-msg-loading">Loading…</span>}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
                <textarea
                  className="field-textarea follow-up-textarea"
                  placeholder="Paste the email you received here, or select one from Gmail above…"
                  value={followUpEmail}
                  onChange={e => setFollowUpEmail(e.target.value)}
                  rows={5}
                />
              </div>
              <div className="follow-up-instructions">
                <label className="field-label" style={{ marginTop: '0.6rem' }}>
                  Custom Instructions <span className="field-label-optional">(optional)</span>
                </label>
                <textarea
                  className="field-textarea follow-up-instructions-textarea"
                  placeholder="e.g. Ask about the interview timeline, mention I'm available immediately, keep it under 3 sentences…"
                  value={followUpInstructions}
                  onChange={e => setFollowUpInstructions(e.target.value)}
                  rows={2}
                />
              </div>
              <button className="action-btn" onClick={handleGenerateFollowUp} disabled={generatingFollowUp || !followUpEmail.trim()} style={{ marginTop: '0.5rem' }}>
                {generatingFollowUp ? <span className="btn-loading"><span className="spin-icon">▶</span> Generating…</span> : '▶ Generate Follow-Up'}
              </button>
              {followUpDraft && (
                <div className="mail-draft-section" style={{ marginTop: '1rem' }}>
                  {followUpDraft.w2_detected && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem', padding: '0.5rem 0.75rem', background: 'rgba(200, 155, 60, 0.15)', border: '1px solid rgba(200, 155, 60, 0.4)', borderRadius: '6px', fontSize: '0.82rem' }}>
                      <span style={{ color: '#c89b3c', fontWeight: 600 }}>W2/Full-Time Detected</span>
                      <span style={{ color: 'rgba(255,255,255,0.6)' }}> — C2C/C2H preference reply generated</span>
                      {followUpDraft.auto_draft_saved && (
                        <span style={{ marginLeft: 'auto', color: '#2ebd73', fontWeight: 600 }}>Draft auto-saved to Gmail</span>
                      )}
                    </div>
                  )}
                  <div className="mail-draft-body">
                    {followUpDraft.to_emails?.length > 0 && (
                      <div className="mail-field">
                        <span className="mail-field-label">To</span>
                        <div className="mail-to-chips">
                          {followUpDraft.to_emails.map((email, i) => <span key={i} className="mail-to-chip">{email}</span>)}
                        </div>
                      </div>
                    )}
                    <div className="mail-field">
                      <span className="mail-field-label">Subject</span>
                      <div className="mail-subject-text">{followUpDraft.subject}</div>
                    </div>
                    <div className="mail-field">
                      <span className="mail-field-label">Body</span>
                      <div className="mail-body-text">{followUpDraft.body}</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', margin: '0.75rem 0', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.5)', marginRight: '0.25rem' }}>Attachments:</span>
                    <button
                      className={`mail-act-btn${fuAttach.resume ? ' mail-gmail-btn' : ''}`}
                      style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}
                      onClick={() => setFuAttach(p => ({ ...p, resume: !p.resume }))}
                    >
                      {fuAttach.resume ? '✓' : '+'} Resume
                    </button>
                    <button
                      className={`mail-act-btn${fuAttach.cover_letter ? ' mail-gmail-btn' : ''}`}
                      style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}
                      onClick={() => setFuAttach(p => ({ ...p, cover_letter: !p.cover_letter }))}
                    >
                      {fuAttach.cover_letter ? '✓' : '+'} Cover Letter
                    </button>
                    {personalDocs.dl ? (
                      <button
                        className={`mail-act-btn${fuAttach.dl ? ' mail-gmail-btn' : ''}`}
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}
                        onClick={() => setFuAttach(p => ({ ...p, dl: !p.dl }))}
                      >
                        {fuAttach.dl ? '✓' : '+'} DL
                      </button>
                    ) : (
                      <label className="mail-act-btn" style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', cursor: 'pointer' }}>
                        {uploadingDoc === 'dl' ? '…' : '↑ Upload DL'}
                        <input type="file" accept=".pdf,.docx,.doc,.png,.jpg,.jpeg" hidden onChange={e => handleUploadDoc('dl', e.target.files[0])} />
                      </label>
                    )}
                    {personalDocs.gc ? (
                      <button
                        className={`mail-act-btn${fuAttach.gc ? ' mail-gmail-btn' : ''}`}
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}
                        onClick={() => setFuAttach(p => ({ ...p, gc: !p.gc }))}
                      >
                        {fuAttach.gc ? '✓' : '+'} GC
                      </button>
                    ) : (
                      <label className="mail-act-btn" style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', cursor: 'pointer' }}>
                        {uploadingDoc === 'gc' ? '…' : '↑ Upload GC'}
                        <input type="file" accept=".pdf,.docx,.doc,.png,.jpg,.jpeg" hidden onChange={e => handleUploadDoc('gc', e.target.files[0])} />
                      </label>
                    )}
                  </div>
                  <div className="mail-draft-actions">
                    <button className="mail-act-btn" onClick={() => {
                      const full = `Subject: ${followUpDraft.subject}\n\n${followUpDraft.body}`;
                      navigator.clipboard.writeText(full); setCopiedField('fu'); setTimeout(() => setCopiedField(null), 2000);
                    }}>
                      {copiedField === 'fu' ? '✓ Copied' : '↑ Copy All'}
                    </button>
                    {followUpDraft.to_emails?.length > 0 && (
                      <a
                        href={`mailto:${followUpDraft.to_emails.join(',')}?subject=${encodeURIComponent(followUpDraft.subject)}&body=${encodeURIComponent(followUpDraft.body)}`}
                        className="mail-act-btn mail-mailto-btn"
                      >
                        ✉ Open in Mail App
                      </a>
                    )}
                    {gmailConnected && (
                      <button className="mail-act-btn mail-gmail-btn" onClick={handleSaveFollowUpToGmail} disabled={savingFollowUp}>
                        {savingFollowUp ? '…' : followUpGmailSaved ? '✓ Saved to Gmail' : '✉ Save to Gmail Drafts'}
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
        </div>

        {/* ── Batch Mode ── */}
        {batchMode && (
          <div className="panel panel-wide panel-enter">
            <div className="panel-tag">
              <span className="panel-num">05</span>
              <span className="panel-title">Batch Production</span>
            </div>
            {error && <div className="error-banner">⚠ {error}</div>}
            {(storedResumes.length === 0 || !selectedResumeName) && (
              <div className="error-banner">⚠ No resume selected — add one in Single Scan mode first.</div>
            )}
            <div className="batch-workspace">
              <div className="batch-input-col">
                <div className="batch-input-header">
                  <label className="field-label" style={{ margin: 0 }}>Job Descriptions</label>
                  <span className="batch-counter" style={batchJds.length >= 10 ? { color: '#ff6b6b' } : undefined}>{batchJds.filter(j => j.trim().length > 50).length} / 10 JDs</span>
                </div>
                <p className="batch-hint">Paste one JD per box · skips JDs requiring &gt;10 yrs experience</p>
                <div className="batch-boxes">
                  {batchJds.map((jd, idx) => (
                    <div key={idx} className="batch-box">
                      <div className="batch-box-header">
                        <span className="batch-box-label">JD #{idx + 1}</span>
                        {jd.trim().length > 0 && <span className="batch-box-chars">{jd.trim().length} chars</span>}
                        {batchJds.length > 1 && (
                          <button className="batch-box-remove" title="Remove" disabled={batchRunning} onClick={() => setBatchJds(prev => prev.filter((_, i) => i !== idx))}>✕</button>
                        )}
                      </div>
                      <textarea
                        className="field-textarea batch-box-textarea"
                        placeholder={`Paste job description #${idx + 1} here...`}
                        value={jd}
                        onChange={e => setBatchJds(prev => prev.map((v, i) => i === idx ? e.target.value : v))}
                        disabled={batchRunning}
                      />
                    </div>
                  ))}
                </div>
                {batchJds.length < 10 && (
                  <button className="batch-add-btn" onClick={() => setBatchJds(prev => [...prev, ''])} disabled={batchRunning}>+ Add JD</button>
                )}
                <div className="batch-btn-row">
                  <label className="batch-upload-label">
                    ↑ Upload .txt
                    <input type="file" accept=".txt,.text" onChange={handleBatchFileUpload} disabled={batchRunning} />
                  </label>
                  <button className={`action-btn${batchRunning ? ' loading' : ''}`} onClick={handleBatchRun} disabled={batchRunning || batchJds.every(j => j.trim().length <= 50) || !selectedResumeName} style={{ flex: 2 }}>
                    {batchRunning ? <span className="btn-loading"><span className="spin-icon">▶</span> Processing…</span> : '▶ Run Batch'}
                  </button>
                </div>
              </div>
              {batchJobs.length > 0 && (
                <div className="batch-results-col">
                  <div className="batch-results-header">
                    <span className="field-label" style={{ margin: 0 }}>Progress</span>
                    <span className="batch-summary">
                      {batchJobs.filter(j => j.status === 'done').length} done
                      {batchJobs.filter(j => j.status === 'skipped').length > 0 && ` · ${batchJobs.filter(j => j.status === 'skipped').length} skipped`}
                      {' '}/ {batchJobs.length}
                    </span>
                  </div>
                  <div className="batch-job-list">
                    {batchJobs.map((job, idx) => (
                      <div key={idx} className={`batch-job batch-job-${job.status}`}>
                        <span className="batch-job-num">{String(idx + 1).padStart(2, '0')}</span>
                        <div className="batch-job-body">
                          <span className="batch-job-company">{job.result?.company_name || `JD #${idx + 1}`}</span>
                          {job.status === 'error' && <span className="batch-job-err">{job.error}</span>}
                          {job.status === 'skipped' && <span className="batch-job-err" style={{ color: '#f0a500' }}>{job.error}</span>}
                        </div>
                        <div className="batch-job-meta">
                          {job.status === 'done' && <span className="batch-job-score" style={{ color: scoreAccent(job.result.score) }}>{job.result.score}%</span>}
                          {job.status === 'done' && job.result?.id && (
                            <>
                              <a href={`http://localhost:8000/api/download/${job.result.file_path.replace(/^trailerd\//, '')}`} className="dl-link" download title="Resume">↓</a>
                              {job.result.pdf_path && (
                                <a href={`http://localhost:8000/api/download/${job.result.pdf_path.replace(/^trailerd\//, '')}`} className="dl-link" download title="Resume PDF">PDF</a>
                              )}
                              <button className="dl-link" title="Open CL & Email panels" onClick={() => { setBatchMode(false); handleSelectRecord(job.result); }}>CL+✉</button>
                            </>
                          )}
                        </div>
                        <span className="batch-status-icon">
                          {job.status === 'pending' && <span className="batch-dot pending">○</span>}
                          {job.status === 'processing' && <span className="batch-dot processing spin-icon">▶</span>}
                          {job.status === 'done' && <span className="batch-dot done">✓</span>}
                          {job.status === 'skipped' && <span className="batch-dot error" title="Skipped">⊘</span>}
                          {job.status === 'error' && <span className="batch-dot error">✕</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Production Log ── */}
        <div className="panel panel-wide panel-enter" style={{ animationDelay: '160ms' }}>
          <div className="panel-top-row">
            <div className="panel-tag inline">
              <span className="panel-num">06</span>
              <span className="panel-title">Production Log</span>
            </div>
            {history.length > 0 && (
              <a href="http://localhost:8000/api/history/csv" className="csv-btn" download>↓ CSV Export</a>
            )}
          </div>

          {history.length > 0 && (
            <div className="history-filters">
              <input
                type="text"
                className="history-search"
                placeholder="Search company…"
                value={historySearch}
                onChange={e => setHistorySearch(e.target.value)}
              />
              <select
                className="history-filter-select"
                value={historyStatusFilter}
                onChange={e => setHistoryStatusFilter(e.target.value)}
              >
                <option value="">All Statuses</option>
                <option value="Scanned">Scanned</option>
                <option value="Applied">Applied</option>
                <option value="Phone Screen">Phone Screen</option>
                <option value="Interview">Interview</option>
                <option value="Offer">Offer</option>
                <option value="Rejected">Rejected</option>
              </select>
              {(historySearch || historyStatusFilter) && (
                <button className="filter-clear-btn" onClick={() => { setHistorySearch(''); setHistoryStatusFilter(''); }}>✕ Clear</button>
              )}
              <span className="history-count">{filteredHistory.length} record{filteredHistory.length !== 1 ? 's' : ''}</span>
            </div>
          )}

          {filteredHistory.length > 0 ? (
            <>
              <table className="history-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th className="sortable-th" onClick={() => toggleSort('company')}>Company {historySortBy === 'company' ? (historySortDir === 'asc' ? '↑' : '↓') : ''}</th>
                    <th className="sortable-th" onClick={() => toggleSort('date')}>Date {historySortBy === 'date' ? (historySortDir === 'asc' ? '↑' : '↓') : ''}</th>
                    <th className="sortable-th" onClick={() => toggleSort('score')}>Score {historySortBy === 'score' ? (historySortDir === 'asc' ? '↑' : '↓') : ''}</th>
                    <th className="sortable-th" onClick={() => toggleSort('status')}>Status {historySortBy === 'status' ? (historySortDir === 'asc' ? '↑' : '↓') : ''}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {pagedHistory.map((item, idx) => (
                    <React.Fragment key={item.id}>
                      <tr className={`history-row${expandedJdId === item.id ? ' jd-open' : ''}`}>
                        <td className="scene-num">{String((computedPage - 1) * HISTORY_PAGE_SIZE + idx + 1).padStart(2, '0')}</td>
                        <td className="company-col">
                          <button className="jd-toggle-btn" onClick={() => toggleJdExpand(item.id)} title={expandedJdId === item.id ? 'Hide JD' : 'Preview JD'}>
                            {expandedJdId === item.id ? '▾' : '▸'}
                          </button>
                          <button
                            className={`company-name-btn${activeRecordId === item.id ? ' active' : ''}`}
                            onClick={() => handleSelectRecord(item)}
                            title="Load cover letter &amp; email draft"
                          >
                            {item.company_name}
                          </button>
                          {item.source === 'job-finder' && <span className="source-tag">finder</span>}
                          {item.rejection_reason && <span className="reject-reason" title={item.rejection_reason}>{item.rejection_reason}</span>}
                        </td>
                        <td className="date-col">
                          {item.created_at ? new Date(item.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                        </td>
                        <td className="score-col">
                          {item.source === 'job-finder' ? (
                            <span className="score-badge" style={{ color: scoreAccent(item.match_percentage || 0) }} title="Job Fit %">{item.match_percentage || 0}%</span>
                          ) : (
                            <span className="score-badge" style={{ color: scoreAccent(item.score) }}>{item.score}%</span>
                          )}
                        </td>
                        <td>
                          <select
                            value={item.status || 'Scanned'}
                            onChange={e => handleStatusChange(item.id, e.target.value)}
                            className={`status-dropdown status-${(item.status || 'Scanned').toLowerCase().replace(' ', '-')}`}
                          >
                            <option value="Scanned">Scanned</option>
                            {item.source === 'job-finder' && <option value="Matched">Matched</option>}
                            <option value="Applied">Applied</option>
                            <option value="Phone Screen">Phone Screen</option>
                            <option value="Interview">Interview</option>
                            <option value="Offer">Offer</option>
                            <option value="Rejected">Rejected</option>
                          </select>
                          {item.status_updated_at && (
                            <div className="status-date">{new Date(item.status_updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</div>
                          )}
                        </td>
                        <td className="actions-col">
                          {item.file_path && (
                            <a href={`http://localhost:8000/api/download/${item.file_path.replace(/^trailerd\//, '')}`} className="dl-link" download title="Download resume">↓</a>
                          )}
                          {item.pdf_path && (
                            <a href={`http://localhost:8000/api/download/${item.pdf_path.replace(/^trailerd\//, '')}`} className="dl-link" download title="Download resume PDF">PDF</a>
                          )}
                          {item.file_path && (
                            <a href={`http://localhost:8000/api/download/${item.file_path.replace(/[^/]+\.docx$/, 'jd_info.txt').replace(/^trailerd\//, '')}`} className="dl-link" download title="Download JD info">JD</a>
                          )}
                          <button className="cl-hist-btn" onClick={() => handleHistoryCL(item.id, item.company_name)} disabled={loadingCLId === item.id} title="Generate cover letter">
                            {loadingCLId === item.id ? '…' : 'CL'}
                          </button>
                          <button className="mail-hist-btn" onClick={() => handleHistoryMail(item.id, item.company_name)} disabled={loadingMailId === item.id} title="Generate email draft">
                            {loadingMailId === item.id ? '…' : '✉'}
                          </button>
                          <button className="rerun-hist-btn" onClick={() => handleRerunFromLog(item)} title="Re-run this JD — updates this company's tailored resume in place">⟳</button>
                          <button className="del-btn" onClick={() => handleDeleteHistory(item.id)} title="Delete record">×</button>
                        </td>
                      </tr>
                      {expandedJdId === item.id && (
                        <tr className="jd-preview-row">
                          <td colSpan="6">
                            <div className="jd-preview-content">
                              <div className="jd-preview-label">Job Description</div>
                              <div className="jd-preview-text">{item.jd_text}</div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>

              {totalPages > 1 && (
                <div className="history-pagination">
                  <button className="page-btn" onClick={() => setHistoryPage(p => Math.max(1, p - 1))} disabled={historyPage === 1}>← Prev</button>
                  <span className="page-info">{historyPage} / {totalPages}</span>
                  <button className="page-btn" onClick={() => setHistoryPage(p => Math.min(totalPages, p + 1))} disabled={historyPage === totalPages}>Next →</button>
                </div>
              )}
            </>
          ) : history.length === 0 ? (
            <p className="empty-log">No productions yet — run your first scan to begin.</p>
          ) : (
            <p className="empty-log">No records match your filter.</p>
          )}
        </div>
      </main>

      {/* ── Cover Letter Modal ── */}
      {historyCLModal && (
        <div className="cl-modal-overlay" onClick={() => { setHistoryCLModal(null); setCopied(false); }}>
          <div className="cl-modal" onClick={e => e.stopPropagation()}>
            <div className="cl-modal-header">
              <span>Cover Letter — {historyCLModal.company_name}</span>
              <button className="cl-modal-close" onClick={() => { setHistoryCLModal(null); setCopied(false); }}>×</button>
            </div>
            <div className="cl-text">{historyCLModal.cover_letter}</div>
            <div className="cl-actions">
              <button className="cl-copy-btn" onClick={() => { navigator.clipboard.writeText(historyCLModal.cover_letter); setCopied(true); setTimeout(() => setCopied(false), 2000); }}>
                {copied ? '✓ Copied' : '↑ Copy'}
              </button>
              {historyCLModal.cl_path && (
                <a href={`http://localhost:8000/api/download/${historyCLModal.cl_path.replace(/^trailerd\//, '')}`} className="cl-download-btn" download>↓ Download .docx</a>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Mail Draft Modal ── */}
      {historyMailModal && (
        <div className="cl-modal-overlay" onClick={() => { setHistoryMailModal(null); setCopiedField(null); setHistoryDraftPath(null); }}>
          <div className="cl-modal mail-modal" onClick={e => e.stopPropagation()}>
            <div className="cl-modal-header">
              <div className="mail-modal-title">
                <span>Email Draft</span>
                <span className="mail-ollama-badge">via OpenAI</span>
              </div>
              <button className="cl-modal-close" onClick={() => { setHistoryMailModal(null); setCopiedField(null); setHistoryDraftPath(null); }}>×</button>
            </div>
            <div className="mail-modal-scroll">
              <div className="mail-modal-company">{historyMailModal.company_name}</div>
              {historyMailModal.to_emails?.length > 0 && (
                <div className="mail-modal-field">
                  <span className="mail-field-label">To</span>
                  <div className="mail-to-chips">
                    {historyMailModal.to_emails.map((email, i) => <span key={i} className="mail-to-chip">{email}</span>)}
                  </div>
                </div>
              )}
              <div className="mail-modal-field">
                <div className="mail-subject-row">
                  <span className="mail-field-label">Subject</span>
                  <button className="mail-copy-small" onClick={() => { navigator.clipboard.writeText(historyMailModal.subject); setCopiedField('ms'); setTimeout(() => setCopiedField(null), 2000); }}>
                    {copiedField === 'ms' ? '✓' : '↑ Copy'}
                  </button>
                </div>
                <div className="mail-subject-text">{historyMailModal.subject}</div>
              </div>
              <div className="mail-modal-field">
                <span className="mail-field-label">Body</span>
                <div className="mail-body-text mail-body-tall">{historyMailModal.body}</div>
              </div>
            </div>
            <div className="mail-modal-actions">
              <button className="mail-act-btn" onClick={() => { navigator.clipboard.writeText(historyMailModal.body); setCopiedField('mb'); setTimeout(() => setCopiedField(null), 2000); }}>
                {copiedField === 'mb' ? '✓ Copied' : '↑ Copy Body'}
              </button>
              {!historyDraftPath ? (
                <button className="mail-act-btn mail-save-btn" onClick={handleSaveHistoryDraft} disabled={historyDraftSaving}>
                  {historyDraftSaving ? '…Saving' : '💾 Save to Folder'}
                </button>
              ) : (
                <a href={`http://localhost:8000/api/download/${historyDraftPath.replace(/^trailerd\//, '')}`} className="mail-act-btn mail-dl-btn" download>
                  ↓ Download .txt
                </a>
              )}
            </div>
          </div>
        </div>
      )}
        </div>
      </div>
    </div>
  );
}

const sidebarStyles = {
  nav: {
    width: '220px',
    backgroundColor: 'var(--surface)',
    borderRight: '1px solid var(--border)',
    padding: '20px 0',
    height: '100vh',
    position: 'sticky',
    top: 0,
    boxSizing: 'border-box',
  },
  navBrand: {
    padding: '0 16px 20px',
    fontWeight: 700,
    fontSize: '0.72rem',
    fontFamily: 'var(--font-mono)',
    color: 'var(--gold)',
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    borderBottom: '1px solid var(--border)',
    marginBottom: '12px',
  },
  navList: {
    listStyle: 'none',
    margin: 0,
    padding: 0,
  },
  navItem: {
    display: 'block',
    width: '100%',
    padding: '10px 16px',
    border: 'none',
    background: 'transparent',
    textAlign: 'left',
    cursor: 'pointer',
    fontSize: '0.78rem',
    fontFamily: 'var(--font-body)',
    color: 'var(--cream-dim)',
    transition: 'background-color 0.2s, color 0.15s',
    borderLeft: '2px solid transparent',
  },
  navItemActive: {
    display: 'block',
    width: '100%',
    padding: '10px 16px',
    border: 'none',
    background: 'var(--gold-dim)',
    textAlign: 'left',
    cursor: 'pointer',
    fontSize: '0.78rem',
    fontFamily: 'var(--font-body)',
    color: 'var(--gold)',
    fontWeight: 600,
    transition: 'background-color 0.2s, color 0.15s',
    borderLeft: '2px solid var(--gold)',
  },
};

