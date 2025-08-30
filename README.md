# Workstation-Cluster-Manager

A simple **distributed cluster system** built with **Python + Docker**.  

It consists of:
- **Server** → receives tasks & coordinates clients  
- **Clients** → connect to the server and execute tasks (scalable using Docker Compose)  

---

## Prerequisites

Before you start, make sure you have:

- [Docker Desktop](https://www.docker.com/products/docker-desktop) installed & running  
- [Visual Studio Code](https://code.visualstudio.com/) (recommended)  
- Python 3.9+ (only needed if you want to run outside Docker)  

Check Docker is working:

```bash
docker ps
docker run -p 8000:5000 cluster_app

Workstation-Cluster-Manager/
├── app.py               # Main server + client logic
├── requirements.txt     # Python dependencies
├── Dockerfile           # One image for both server & client
├── docker-compose.yml   # Orchestrates server + scalable clients
├── shared/              # Shared scripts
│   ├── aa.py
│   ├── bb.py
│   ├── cc.py
│   └── render_video.py
└── README.md            # This file

docker compose up --build --scale client=4

http://localhost:8000

## Stop the cluster
