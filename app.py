from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import time
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from undetected_chromedriver import Chrome, ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from io import BytesIO
from bs4 import BeautifulSoup
import requests
import os

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')  # Dynamic secret key

# Global driver instance to maintain the session across requests
driver = None

# Function to initialize WebDriver
def initialize_driver():
    global driver
    if driver is None:
        try:
            chrome_options = ChromeOptions()
            chrome_options.add_argument("--headless")  # Run in headless mode (no UI)
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")  # Prevent GPU errors in headless mode
            driver = Chrome(options=chrome_options)
            driver.maximize_window()
        except Exception as e:
            raise Exception(f"Error initializing WebDriver: {e}")

# Route for the login page
@app.route('/', methods=['GET', 'POST'])
def login():
    global driver

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Initialize driver
        try:
            initialize_driver()
        except Exception as e:
            flash(f"{e}", 'error')
            return redirect(url_for('login'))

        # Run Selenium logic to handle login and scraping
        result, df = login_and_scrape(email, password)

        if result == 'success':
            flash("Login Successful! Data is being downloaded...", 'success')
            return send_file(create_excel_file(df), download_name="downloaded_data.xlsx", as_attachment=True)
        else:
            flash(result, 'error')
            cleanup()  # Clean up driver
            return redirect(url_for('login'))

    return render_template('index.html')

# Function to log in and scrape data
def login_and_scrape(email, password):
    try:
        # Navigate to login page
        driver.get("https://expert.chegg.com/")
        driver.maximize_window()

        # Login process
        email_tag = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#username')))
        email_tag.send_keys(Keys.CONTROL + 'a' + Keys.BACKSPACE)
        email_tag.send_keys(email)

        pass_tag = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#password')))
        pass_tag.send_keys(Keys.CONTROL + 'a' + Keys.BACKSPACE)
        pass_tag.send_keys(password)

        submit_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '/html/body/div/main/section/div/div/div/form/div[2]/button'))
        )
        submit_button.click()

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'My Past Activities') or contains(text(), 'Wrong email or password')]"))
        )
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        text = soup.get_text()

        if 'Wrong email or password' in text:
            return "Wrong email or password. Please enter correct details again.", None

        if 'My Past Activities' in text:
            # Login successful, proceed to scrape
            data = scrape_data()
            return "success", data

        return "An unexpected error occurred. Please try again.", None

    except Exception as e:
        print(f"An error occurred during the login and scrape process: {e}")
        return "An error occurred. Please try again.", None

# Function to scrape data after login
def scrape_data():
    q_url = 'https://expert.chegg.com/qna/authoring/myanswers'
    driver.get(q_url)
    cooky = driver.get_cookies()
    cookie_string = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cooky])

    try:
        p_url = 'https://expert-gateway.chegg.com/nestor-graph/graphql'
        headers = {
            "Host": "expert-gateway.chegg.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Authorization": "Basic alNNNG5iVHNXV0lHR2Y3OU1XVXJlQjA3YmpFeHJrRzM6SmQxbTVmd3o3aHRobnlCWg==",
            "Cookie": cookie_string,
        }
        form_d = {
            "operationName": "myAnswers",
            "query": "query myAnswers($last: Int!, $first: Int!, $filters: AnswerFilters) {\n  myAnswers(last: $last, first: $first, filters: $filters) {\n    edges {\n      node {\n        answeredDate\n        id\n        uuid\n        isStructuredAnswer\n        isDeleted\n        question {\n          language\n          body\n          title\n          isDeleted\n          subject {\n            subjectGroup {\n              name\n              __typename\n            }\n            __typename\n          }\n          uuid\n          id\n          questionTemplate {\n            templateName\n            templateId\n            __typename\n          }\n          __typename\n        }\n        studentRating {\n          negative\n          positive\n          __typename\n        }\n        qcReview {\n          overallQcRating\n          isInvalid\n          isQcOfQcRating\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    totalResults\n    pageInfo {\n      startCursor\n      __typename\n    }\n    __typename\n  }\n}",
            "variables": {
                "filters": {"lookbackPeriod": "ALL", "rating": "ALL"},
                "first": 0,
                "last": 20,
            },
        }

        res = requests.post(p_url, json=form_d, headers=headers)
        res.raise_for_status()
        data = res.json()
        edges = data.get('data', {}).get('myAnswers', {}).get('edges', [])
        all_dicts = []

        for edge in edges:
            try:
                question_body = edge['node']['question']['body']
                question_id = edge['node']['question']['id']
                soup = BeautifulSoup(question_body, 'html.parser')
                question_text = soup.get_text(strip=True)
                all_dicts.append({
                    'question': question_text,
                    'url': f'https://www.chegg.com/homework-help/questions-and-answers/q{question_id}',
                })
            except Exception as e:
                print(f"Error processing question: {e}")
                continue

        return pd.DataFrame(all_dicts)

    except Exception as e:
        print(f"An error occurred: {e}")
        return pd.DataFrame()

# Function to create Excel file from DataFrame
def create_excel_file(df):
    output = BytesIO()
    if df.empty:
        df = pd.DataFrame({'Message': ['No data available']})
    df.to_excel(output, index=False)
    output.seek(0)
    return output

# Ensure proper cleanup when the app is stopped
@app.teardown_appcontext
def cleanup(exception=None):
    global driver
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        finally:
            driver = None
