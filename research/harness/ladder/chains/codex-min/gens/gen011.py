import re

parse=lambda t:dict(re.findall('(.+) = (.*)',t))
