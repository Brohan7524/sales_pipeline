import mysql.connector

conn = mysql.connector.connect(host="localhost", user="root", password="yourpassword")
cursor = conn.cursor()

cursor.execute("CREATE DATABASE IF NOT EXISTS bronze;")
cursor.execute("CREATE DATABASE IF NOT EXISTS silver;")
cursor.execute("CREATE DATABASE IF NOT EXISTS gold;")

conn.commit()
conn.close()