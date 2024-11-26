from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import time
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from undetected_chromedriver import Chrome,ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from io import BytesIO
from bs4 import BeautifulSoup
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Needed for flashing messages

# Global driver instance to maintain the session across requests
driver = None

# Route for the login page
@app.route('/', methods=['GET', 'POST'])
def login():
    global driver
    
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Initialize driver only if it's not already initialized
        if driver is None:
            chrome_options = ChromeOptions()
            chrome_options.add_argument("--headless")  # Run in headless mode (no UI)
            driver = Chrome(options=chrome_options)
            driver.maximize_window()
        
        # Run Selenium logic to handle login and scraping
        result, df = login_and_scrape(email, password)
        
        if result == 'success':
            flash("Login Successful! Data is being downloaded...", 'success')
            return send_file(create_excel_file(df), download_name ="downloaded_data.xlsx", as_attachment=True)
        else:
            flash(result, 'error')
            driver.quit()  # Quit the driver if login fails
            driver = None  # Reset the driver instance
            return redirect(url_for('login'))  # Redirect to login page
    
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

        submit_button = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, '/html/body/div/main/section/div/div/div/form/div[2]/button')))
        submit_button.click()

        time.sleep(5)  # Wait for login to complete
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        text = soup.get_text()

        if 'Wrong email or password' in text:
            return "Wrong email or password. Please enter correct details again.", None

        if 'My Past Activities' in text:
            # Login successful, proceed to scrape
            print('Login successful')
            data = scrape_data()
            return "success", data

        return "An unexpected error occurred. Please try again.", None

    except Exception as e:
        print(f"An error occurred during the login and scrape process: {e}")
        return "An error occurred. Please try again.", None


# Function to scrape data after login
def scrape_data():
    # Navigate to the desired URL for scraping
    q_url='https://expert.chegg.com/qna/authoring/myanswers'
    driver.get(q_url)
    cooky=driver.get_cookies()
    cookie_string = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cooky])
    try:
        p_url='https://expert-gateway.chegg.com/nestor-graph/graphql'
        headers = {
            "Host": "expert-gateway.chegg.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": "https://expert.chegg.com/",
            "Content-Type": "application/json",
            "apollographql-client-name": "chegg-web-producers",
            "apollographql-client-version": "main-157f7fd2-1548443150",
            "Authorization": "Basic alNNNG5iVHNXV0lHR2Y3OU1XVXJlQjA3YmpFeHJrRzM6SmQxbTVmd3o3aHRobnlCWg==",
            "Origin": "https://expert.chegg.com",
            "Sec-GPC": "1",
            "Connection": "keep-alive",
            "Cookie":cookie_string,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Priority": "u=4"
        }
        form_d={
        "operationName": "myAnswers",
        "query": "query myAnswers($last: Int!, $first: Int!, $filters: AnswerFilters) {\n  myAnswers(last: $last, first: $first, filters: $filters) {\n    edges {\n      node {\n        answeredDate\n        id\n        uuid\n        isStructuredAnswer\n        isDeleted\n        question {\n          language\n          body\n          title\n          isDeleted\n          subject {\n            subjectGroup {\n              name\n              __typename\n            }\n            __typename\n          }\n          uuid\n          id\n          questionTemplate {\n            templateName\n            templateId\n            __typename\n          }\n          __typename\n        }\n        studentRating {\n          negative\n          positive\n          __typename\n        }\n        qcReview {\n          overallQcRating\n          isInvalid\n          isQcOfQcRating\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    totalResults\n    pageInfo {\n      startCursor\n      __typename\n    }\n    __typename\n  }\n}",
        "variables": {
            "filters": {
                "lookbackPeriod": "ALL",
                "rating": "ALL"
            },
            "first": 0,
            "last": 20
        }}
        res = requests.post(p_url, json=form_d, headers=headers)
        res.raise_for_status()  # Raise an HTTPError for bad responses
        a = res.json()
        total_results = a.get('data', {}).get('myAnswers', {}).get('totalResults', 0)

        # Check if total_results > 20, if so, request all data
        if total_results > 20:
            form_d={
            "operationName": "myAnswers",
            "query": "query myAnswers($last: Int!, $first: Int!, $filters: AnswerFilters) {\n  myAnswers(last: $last, first: $first, filters: $filters) {\n    edges {\n      node {\n        answeredDate\n        id\n        uuid\n        isStructuredAnswer\n        isDeleted\n        question {\n          language\n          body\n          title\n          isDeleted\n          subject {\n            subjectGroup {\n              name\n              __typename\n            }\n            __typename\n          }\n          uuid\n          id\n          questionTemplate {\n            templateName\n            templateId\n            __typename\n          }\n          __typename\n        }\n        studentRating {\n          negative\n          positive\n          __typename\n        }\n        qcReview {\n          overallQcRating\n          isInvalid\n          isQcOfQcRating\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    totalResults\n    pageInfo {\n      startCursor\n      __typename\n    }\n    __typename\n  }\n}",
            "variables": {
                "filters": {
                    "lookbackPeriod": "ALL",
                    "rating": "ALL"
                },
                "first": 0,
                "last": total_results
            }}
            res = requests.post(p_url, json=form_d, headers=headers)
            res.raise_for_status()  # Raise an HTTPError for bad responses
            a = res.json()
            b = a['data']['myAnswers']['edges']
        else:
            b = a['data']['myAnswers']['edges']

        # Initialize list to hold the question data
        all_dicts = []

        # Process each question if data is available
        for i in b:
            try:
                c = i['node']['question']['body']
                s_c = BeautifulSoup(c, 'html.parser')
                q_t = s_c.get_text(strip=True)
                q_id = i['node']['question']['id']
                dict_ = {'question': q_t, 'url': f'https://www.chegg.com/homework-help/questions-and-answers/q{q_id}'}
                all_dicts.append(dict_)
            except Exception as e:
                print(f"Error processing question: {e}")
                continue  # Skip this entry if error occurs

        # If questions are found, create a DataFrame
        if len(all_dicts):
            df = pd.DataFrame(all_dicts)
        else:
            print("No data found")
            df = pd.DataFrame()  # Return empty DataFrame if no data is found

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        df = pd.DataFrame()  # Return empty DataFrame if the request fails
    except Exception as e:
        print(f"An error occurred: {e}")
        df = pd.DataFrame()  # Return empty DataFrame for any other errors

    return df

# Function to create Excel file from DataFrame
def create_excel_file(df):
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return output

# Ensure proper cleanup when the app is stopped
@app.teardown_appcontext
def cleanup(exception=None):
    global driver
    if driver:
        driver.quit()
        driver = None
