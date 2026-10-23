"""Absolute launcher path makes project process ownership auditable on Windows."""
import runpy
import sys
module={'detector':'campus_detection.http_service','ocr':'campus_ocr.http_service'}[sys.argv.pop(1)]
runpy.run_module(module,run_name='__main__')
