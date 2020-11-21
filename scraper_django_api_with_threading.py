# WITH THREADING - PERFORMANCE IMPROVEMENT FOR BIGGER DATASET

# For Handling API requests and Parsing Data
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from rest_framework import status
from rest_framework.renderers import JSONRenderer, JSONOpenAPIRenderer
from scrapper.models import Recipient, Slug, Product
from rest_framework.generics import ListAPIView
from .serializers import ProductSerializer
from datetime import datetime

# Selenium Scrapper
import selenium
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

# Email Client
from mailjet_rest import Client

# Beautiful Soup
from bs4 import BeautifulSoup

import os
from django.conf import settings


class ScrapWeb(APIView):
    """Scraps web and find the price, image_url and name of the product"""

    parser_classes = [JSONParser]
    renderer_classes = [JSONOpenAPIRenderer]

    # Emailing API
    def emailer(self, body, email, name):
        api_key = "#####################################"
        api_secret = "#####################################"
        mailjet = Client(auth=(api_key, api_secret), version="v3.1")
        data = {
            "Messages": [
                {
                    "From": {"Email": "neoyumnam@gmail.com", "Name": "Ningthem"},
                    "To": [{"Email": email, "Name": name}],
                    "Subject": "Important: Current prices",
                    "HTMLPart": body,
            
                    "CustomID": "AppGettingStartedTest",
                }
            ]
        }
        result = mailjet.send.create(data=data)

    # Function to be called in Threading
    def multiscraper(self, slugs, products_scrapped):
        """Scrap web pages. To be used as a function in multi-threading"""

        ABS_PATH = os.path.dirname(os.path.abspath(__file__))
        DRIVER_PATH = os.path.join(ABS_PATH, "chromedriver.exe")

        options = webdriver.ChromeOptions()
        options.headless = True
        options.add_argument("window-size=1366x768")    # Very important

        # Initiate a browsere Instance in a thread
        browser = webdriver.Chrome(
        executable_path=DRIVER_PATH,
        options=options,
        )

        # Start scraping
        for slug in slugs:
            browser.get(f"https://django-react-ecommerce.vercel.app/products/{slug}")

            try:
                #Wait is necessary in case the website is loaded dynamically using Javascript libraries like React, Angular, Vue JS etc
                WebDriverWait(browser, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".product-details-content > h3"))
                )

                # Get Page source from browser
                page_source = browser.page_source

                """
                Beautiful soup initialization. Scraping through Selenium is possible but sometimes slower. So, BeautifulSoup
                is used to continue scraping from Selenium
                """
                soup = BeautifulSoup(page_source, 'lxml')
                price_elem = soup.find('div', class_='product-details-content').find('h3').get_text()[1:]
                name_elem = soup.find('div', class_='product-details-content').find('h2').get_text()
                image_elem = soup.find('div', class_='product-dec-right').find('img').get('src')
                
                #Recorded data in dictionary   
                products_scrapped[slug] = [slug, price_elem, image_elem, name_elem]


            except [TimeoutException, AttributeError, NameError]:
                print("Timeout")
        browser.quit()

    def get(self, request):
        web_url = "https://django-react-ecommerce.vercel.app/products/"

        # Getting Slugs for scraping
        slugs = Slug.objects.all()
        slug_list = [product.slug for product in slugs]

        # Using only 2 threads now, so diving the slugs to 2 chunks and each will run on a thread
        slugs_half_len = round(len(slug_list) / 2)
        slugs_divided = [slug_list[:slugs_half_len], slug_list[slugs_half_len:]]
        
        # Initiating dictionary for products scraped
        products_scrapped = dict()

        # Initialize threads for multi-threading
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = [executor.submit(self.multiscraper, slugs, products_scrapped) for slugs in slugs_divided]

        # Saving products to database
        for name, item in products_scrapped.items():
            slug, latest_price, image_url, product_name = item[0], item[1], item[2], item[3]

            product = Product.objects.filter(slug=slug).first()
            
            # If new product
            if not product:
                new_product = Product(name=product_name, slug=slug, latest_price=latest_price, image_url=image_url, url=f'{web_url}{slug}')
                new_product.save()
            else:
                product.old_price = product.latest_price
                product.latest_price = latest_price
                product.save()

        all_products = Product.objects.all()

        email_body = ""
        diff_ind = False   # Indicator if email needs sending
        for product in all_products:
            # Compiling email template if difference present

            if(product.old_price > product.latest_price):
                email_body += f"""
                <h3>{product.name}</h3>
                <img src="{product.image_url}" width="200px" alt="">
                <br>
                <b>OldPrice: ${product.old_price}</b> <br>
                <b>New Price: ${product.latest_price}</b>
                <br>
                <b>Price dropped by ${product.old_price - product.latest_price}</b>
                <hr>
                """
                diff_ind = True  #Sets to true if any product has price change

        # Sending email if difference present   
        if diff_ind == True:
            recipients = Recipient.objects.all()
            for person in recipients:
                self.emailer(body=email_body, email=person.email, name=person.email)
        else:
            print("No Difference")
        return Response({"message": "Scrap Completed", "success_status": 1}, status=status.HTTP_200_OK)


class ListProductAPI(ListAPIView):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()