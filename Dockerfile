FROM python:3.11-slim

RUN apt-get update && apt-get install -y wget zip

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

CMD ["waitress-serve", "--listen=0.0.0.0:8080", "app:app"]
