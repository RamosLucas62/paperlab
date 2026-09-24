FROM python:3.12.14-slim
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY apps/api /app/apps/api
COPY packages /app/packages
COPY fixtures /app/fixtures
ENV PYTHONPATH=/app/apps/api
CMD ["uvicorn", "paperlab.main:app", "--host", "0.0.0.0", "--port", "8000"]
