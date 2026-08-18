import uvicorn

from .settings import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "api_server.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        access_log=True,
    )


if __name__ == "__main__":
    main()

