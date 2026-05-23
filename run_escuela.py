from waitress import serve

from config.wsgi import application


if __name__ == '__main__':
    serve(application, host='127.0.0.1', port=8005, threads=24)