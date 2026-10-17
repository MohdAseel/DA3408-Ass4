import sys
import threading

import captioner
import metrics
from streamlit.web import cli

metrics.start_metrics_server()
threading.Thread(target=captioner.get_captioner, name="model-loader", daemon=True).start()

sys.argv = ["streamlit", "run", "app.py", *sys.argv[1:]]
sys.exit(cli.main())
