import os

from dotenv import load_dotenv
from waitress import serve

from app import app


load_dotenv()


if __name__ == "__main__":
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8080"))
    threads = int(os.getenv("WAITRESS_THREADS", "8"))
    serve(app, host=host, port=port, threads=threads)
