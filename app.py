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
        import uvicorn
        uvicorn.run("server:app", host="0.0.0.0" if os.getenv("K_SERVICE") else "127.0.0.1",
                    port=int(os.getenv("PORT", "8502")))
