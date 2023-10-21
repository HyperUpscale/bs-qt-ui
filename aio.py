import requests
import concurrent.futures


def async_fetch(url):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(requests.get, url)
        concurrent.futures.wait([future, ])
        return future


def main():
    res = async_fetch("https://homepage.bg")
    print(res.done())


if __name__ == '__main__':
    main()