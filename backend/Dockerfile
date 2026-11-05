FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 libxrender1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c "from OCP.STEPControl import STEPControl_Writer; STEPControl_Writer()"
RUN useradd --create-home --uid 10001 app && mkdir /data && chown app:app /data
COPY --chown=app:app app ./app
USER app
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
