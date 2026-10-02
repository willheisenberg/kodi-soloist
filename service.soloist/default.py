import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "resources", "lib"))

import service

service.run()
