# docker/simulation.Dockerfile — Python FastAPI simulation engine image.
# Owner: Member 6
#
# Deliberately kept OUTSIDE simulation/ (that directory belongs to Member 3;
# this Dockerfile only packages it, it doesn't change anything inside it).
# Built with build context = repo root (see docker-compose.yml) so it can
# copy every sibling package simulation/runner.py imports from
# (shared/, robot_agent/, collision_engine/, planner/, edge/).

FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn

COPY shared/ shared/
COPY planner/ planner/
COPY robot_agent/ robot_agent/
COPY collision_engine/ collision_engine/
COPY edge/ edge/
COPY simulation/ simulation/

ENV PYTHONUNBUFFERED=1
EXPOSE 8001

CMD ["python", "-m", "simulation.runner"]
