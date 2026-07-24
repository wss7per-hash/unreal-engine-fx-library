# main.py -- entry point for the FX Library standalone client.

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.ui.main_window import main

if __name__ == "__main__":
    main()
