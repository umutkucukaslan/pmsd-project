import configparser
import logging

config = configparser.ConfigParser()
config.read("./config.ini")

logging.root.setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

# Create handlers
c_handler = logging.StreamHandler()
f_handler = logging.FileHandler(config['Logging'].get('log_file_pth'))
c_handler.setLevel(logging.DEBUG)
f_handler.setLevel(logging.DEBUG)

# Create formatters and add it to handlers
c_format = logging.Formatter('%(asctime)s: %(levelname)s - %(message)s')
f_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
c_handler.setFormatter(c_format)
f_handler.setFormatter(f_format)

# Add handlers to the logger
logger.addHandler(c_handler)
logger.addHandler(f_handler)