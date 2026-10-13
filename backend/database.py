from threading import Lock
import os
import mysql.connector

student_request_lock = Lock()


