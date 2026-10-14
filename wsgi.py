import os

from main import FPGAVisualizationApp

app = FPGAVisualizationApp().app


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
    )
