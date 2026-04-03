"""
Entry point for Streamlit Community Cloud deployment.
Dashboard de veille recrutement tech France.
"""
import sys
import os

# Add dashboard/src to path so all imports (storage, scoring, pipeline…) work
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "src"))

from dashboard import main

main()
