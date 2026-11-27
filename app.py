import os
import sys


if __name__ == "__main__":
    if "streamlit" in sys.modules:
        import streamlit as st
        st.title("HandoffGuard review desk")
        st.write("Start the final review server from the project folder.")
        st.code(r".\.venv\Scripts\python.exe app.py")
        st.link_button("Open review desk", "http://localhost:8502/")
    else:
        import argparse
        from getpass import getpass
        import uvicorn

        parser = argparse.ArgumentParser(description="Start the HandoffGuard review desk")
        parser.add_argument("--gemini", action="store_true", help="Prompt for missing Gemini API credentials")
        parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8502")))
        args = parser.parse_args()
        if args.gemini:
            if not os.getenv("GEMINI_API_KEY"):
                os.environ["GEMINI_API_KEY"] = getpass("Gemini API key (hidden): ").strip()
            if not os.getenv("GEMINI_MODEL"):
                os.environ["GEMINI_MODEL"] = input("Model ID from AI Studio: ").strip()
            if not os.environ["GEMINI_API_KEY"] or not os.environ["GEMINI_MODEL"]:
                parser.exit(2, "A key and model ID are required for API mode.\n")

        uvicorn.run("server:app", host="0.0.0.0" if os.getenv("K_SERVICE") else "127.0.0.1",
                    port=args.port)
