from selenium import webdriver
from selenium.common import WebDriverException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import time
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()


class MetroScraper:
    def __init__(self, driver_path, parse_brand=False):
        self.base_url = "https://online.metro-cc.ru"
        self.driver_path = driver_path
        self.parse_brand = parse_brand

        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        try:
            service = Service(self.driver_path)
            self.driver = webdriver.Chrome(service=service, options=options)
        except WebDriverException as e:
            raise RuntimeError(f"Ошибка при запуске драйвера")

    def change_city(self, new_city):
        try:
            city_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.header-address__receive-button"))
            )
            city_button.click()

            pickup_option = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Самовывоз')]"))
            )
            pickup_option.click()

            change_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Изменить')]"))
            )
            change_button.click()

            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "modal-city__center"))
            )

            time.sleep(2)

            try:
                city_option = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, f"//div[@class='city-item' and contains(text(), '{new_city}')]"))
                )
                city_option.click()
            except Exception as e:
                logging.warning(f"Первый XPath не сработал")
                try:
                    city_option = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(
                            (
                                By.XPATH,
                                f"//div[@class='city-item city-item_active' and contains(text(), '{new_city}')]"))
                    )
                    city_option.click()
                except Exception as e:
                    logging.warning(f"Второй XPath тоже не сработал")

            time.sleep(2)

            select_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(@class, 'delivery__btn-apply') and .//span[text()='Выбрать']]"))
            )
            select_button.click()
            logging.info(f'Город {new_city} выбран')

        except Exception as e:
            logging.warning(f"Ошибка при смене города на {new_city}: {e}")

    def confirm_age(self):
        try:
            age_confirmation_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[span[contains(text(), 'Да, мне есть 18')]]"))
            )
            age_confirmation_button.click()
            logging.info("Возраст подтвержден")
        except Exception as e:
            logging.warning(f"Не найдена форма для подтверждения")

    def load_all_products(self):
        logging.info('Начинаем раскрытие...')
        count = 0
        while True:

            try:
                load_more_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button.simple-button.reset-button.subcategory-or-type__load-more"))
                )
                load_more_button.click()
                time.sleep(3)
                count += 1
            except Exception as e:
                logging.info(f'Раскрыли {count} раз(-а)')
                break
        logging.info('Закончили раскрытие')

    def parse_brand_from_page(self, product_url):
        try:
            self.driver.get(product_url)
            try:
                brand_element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".product-attributes__list-item a.product-attributes__list-item-link"))
                )
                brand = brand_element.text.strip() if brand_element else None
            except TimeoutException:
                logging.warning("Не удалось найти элемент с брендом на странице товара.")
                brand = None
            return brand
        except Exception as e:
            logging.warning(f"Ошибка при парсинге бренда с {product_url}")
            return None

    def parse_category(self, category_slug, city):
        url = f"{self.base_url}/category/{category_slug}"
        data = []

        self.driver.get(url)
        time.sleep(2)

        self.confirm_age()
        self.change_city(city)

        time.sleep(5)

        self.load_all_products()

        try:
            products = self.driver.find_elements(By.CSS_SELECTOR, ".product-card")
            if not products:
                return data
            for i, product in enumerate(products, 1):
                logging.info(f'{i} товар')

                try:
                    old_price_element = product.find_elements(By.CSS_SELECTOR,
                                                              ".product-unit-prices__old-wrapper .product-price__sum "
                                                              ".product-price__sum-rubles")
                    actual_price_element = product.find_element(By.CSS_SELECTOR,
                                                                ".product-unit-prices__actual-wrapper "
                                                                ".product-price__sum .product-price__sum-rubles")

                    old_price = old_price_element[0].text.strip() if old_price_element else None
                    actual_price = actual_price_element.text.strip() if actual_price_element else None

                    regular_price = old_price if old_price else actual_price
                    promo_price = actual_price if old_price else None

                    item = {
                        "id": product.get_attribute("data-sku"),
                        "name": product.find_element(By.CSS_SELECTOR, ".product-card-name__text").text.strip(),
                        "link": product.find_element(By.CSS_SELECTOR, "a").get_attribute("href"),
                        "regular_price": regular_price,
                        "promo_price": promo_price,
                        "city": city,
                    }

                    data.append(item)
                except Exception as e:
                    logging.warning(f"Ошибка при сборе данных товара")

        except Exception as e:
            logging.warning(f"Ошибка парсинга")
            return data

        if self.parse_brand:
            logging.info("Начинаем сбор брендов...")
            for i, item in enumerate(data, 1):
                try:
                    logging.info(i)
                    item["brand"] = self.parse_brand_from_page(item["link"])
                    logging.info(f"Бренд обновлен: {item['brand']}")
                except Exception as e:
                    logging.warning(f"Ошибка при сборе бренда для {item['name']}")

        return data

    def quit(self):
        self.driver.quit()


# Главный скрипт
if __name__ == "__main__":
    default_driver_path = r"C:\Users\Mark\Downloads\chromedriver-win64\chromedriver-win64\chromedriver.exe"
    driver_path = input(f"Введите путь к chromedriver (по умолчанию: {default_driver_path}): ").strip()
    parse_brand = input("Хотите парсить данные о бренде? Это займет больше времени. (да/нет): ").strip().lower() == "да"

    try:
        metro_scraper = MetroScraper(driver_path, parse_brand=parse_brand)
        logging.info("Драйвер успешно инициализирован.")
    except (FileNotFoundError, RuntimeError) as e:
        logging.error(str(e))
        exit(1)

    cities = ["Санкт-Петербург", "Москва"]

    all_data = []

    category_slugs = [
        "chaj-kofe-kakao/kofe/kofe-v-zernakh?in_stock=1",
    ]

    for city in cities:
        for slug in category_slugs:
            logging.info(f"Парсинг категории '{slug}' для города: {city}")
            all_data.extend(metro_scraper.parse_category(slug, city))

    if parse_brand:
        df_with_brand = pd.DataFrame(all_data)
        df_with_brand.to_csv("products_with_brand.csv", index=False)
        logging.info("Данные с брендом успешно сохранены в файл products_with_brand.csv")
    else:
        df_without_brand = pd.DataFrame(all_data)
        df_without_brand.to_csv("products_without_brand.csv", index=False)
        logging.info("Данные без бренда успешно сохранены в файл products_without_brand.csv")

    metro_scraper.quit()
