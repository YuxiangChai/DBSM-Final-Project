from flask import Flask, render_template, request, session, redirect, url_for, send_file
import pymysql
import uuid
from functools import wraps
from datetime import datetime
from dateutil import relativedelta
import hashlib
import onnxruntime as ort
import numpy as np

app = Flask(__name__)
app.secret_key = "secret key"
connection = pymysql.connect(host='cyxserver.mysql.database.azure.com', user='cyxadmin', password='123456A!', 
                             db='Insurance', charset='utf8mb4',
                             cursorclass=pymysql.cursors.DictCursor, autocommit=True,
                             ssl={'fake_flag_to_enable_tls':True})


def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if not 'username' in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return dec

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('home'))
    return render_template('index.html')

@app.route('/login', methods=['GET'])
def login():
    return render_template('login.html')

@app.route('/register', methods=['GET'])
def register():
    return render_template('register.html')

@app.route('/loginAuth', methods=['POST'])
def loginAuth():
    if request.form:
        requestData = request.form
        username = requestData['username']
        password = requestData['password']
        password = hashlib.sha256(password.encode("utf-8")).hexdigest()

        with connection.cursor() as cursor:
            query = 'SELECT * FROM acct_member WHERE username = %s AND password = %s'
            cursor.execute(query, (username, password))
        data = cursor.fetchone()
        if data:
            session['username'] = username
            return redirect(url_for('home'))

        error = 'Incorrect username or password.'
        return render_template('login.html', error=error)

    error = "An unknown error has occurred. Please try again."
    return render_template("login.html", error=error)

@app.route('/registerAuth', methods=["POST"])
def registerAuth():
    if request.form:
        requestData = request.form
        username = requestData['username']
        password = requestData['password']
        password = hashlib.sha256(password.encode("utf-8")).hexdigest()
        firstName = requestData['fname']
        lastName = requestData['lname']
        middleInit = requestData['midinit']
        dob = requestData['dob']
        dob = datetime.strptime(dob, '%m/%d/%Y')
        age = relativedelta.relativedelta(datetime.now().date(), dob).years
        gender = requestData['gender']
        email = requestData['email']
        ssn = requestData['ssn']
        n_children = requestData['n_children']
        smoke = requestData['smoke']
        region = requestData['region']
        bmi = requestData['bmi']
        
        try:
            with connection.cursor() as cursor:
                query = 'SELECT * FROM acct_member WHERE Username = %s'
                cursor.execute(query, (username))
                if cursor.fetchone():
                    error = "%s is already taken." % (username)
                    return render_template('register.html', error=error)
                query = 'INSERT INTO customer (First_name, Last_name, Middle_init, DOB, Gender, Email, SSN) VALUES (%s, %s, %s, %s, %s, %s, %s)'
                cursor.execute(query, (firstName, lastName, middleInit, dob, gender, email, ssn))
                query = 'INSERT INTO acct_member (Username, Password, Start_date, SSN) VALUES (%s, %s, %s, %s)'
                cursor.execute(query, (username, password, datetime.now().date(), ssn))
                query = 'INSERT INTO cust_info (SSN, Age, Gender, Children, Smoker, Region, Bmi) VALUES (%s, %s, %s, %s, %s, %s, %s)'
                cursor.execute(query, (ssn, age, gender, n_children, smoke, region, bmi))
        except pymysql.err.IntegrityError:
            error = 'Error.'
            return render_template('register.html', error=error)

        return redirect(url_for("login"))

    error = "An error has occurred. Please try again."
    return render_template("register.html", error=error)

@app.route("/logout", methods=["GET"])
def logout():
    session.pop("username")
    return redirect("/")

@app.route('/home', methods=['GET'])
@login_required
def home():
    return render_template('home.html')

@app.route('/premium', methods=['GET'])
def premium():
    sess = ort.InferenceSession('model/lreg.onnx')
    input_name = sess.get_inputs()[0].name

    with connection.cursor() as cursor:
        query = 'SELECT i.age, i.gender, i.children, i.smoker, i.region, i.bmi \
                    FROM acct_member a, cust_info i WHERE a.ssn = i.ssn AND a.username = %s'
        cursor.execute(query, (session['username']))
        data = cursor.fetchone()
    
    age = data['age']
    gender = data['gender']
    n_children = data['children']
    smoke = data['smoker']
    region = data['region']
    bmi = data['bmi']

    inp = np.zeros(16)
    inp[0] = bmi

    def set_age(age):
        if age <= 20:
            return 1
        elif age <= 30:
            return 2
        elif age <= 40:
            return 3
        elif age <= 50:
            return 4
        elif age <= 60:
            return 5
        else:
            return 6
        
    age_class = set_age(age)
    if age_class > 1:
        inp[age_class-1] = 1
    inp[6] = 1 if gender == 'male' else 0

    def set_children(n_children):
        if n_children > 5:
            return 5
        return n_children
    children_class = set_children(n_children)
    if children_class > 0:
        inp[6+children_class] = 1
    inp[12] = 1 if smoke == 'yes' else 0
    if region == 'northwest':
        inp[13] = 1
    elif region == 'southeast':
        inp[14] = 1
    elif region == 'southwest':
        inp[15] = 1

    pred_onx = sess.run(None, {input_name: inp.astype(np.float32)})[0][0][0]
    return render_template('premium.html', pre=pred_onx)

@app.route('/billing', methods=['GET'])
@login_required
def billing():
    with connection.cursor() as cursor:
        query = 'SELECT b.BAccount_name, b.Baddress1, b.Baddress2, b.BCity, b.BState, b.BZip \
                    FROM billing_account b, member_billing mb WHERE mb.username = %s AND \
                        mb.baccount_name = b.baccount_name'
        cursor.execute(query, (session['username']))
    data = cursor.fetchall()
    return render_template('billing.html', data=data)

@app.route('/addBilling', methods=['POST'])
@login_required
def addBilling():
    if request.form:
        requestData = request.form
        bacctName = requestData['bacctName']
        bacctName2 = requestData['bacctName2']
        bAddress1 = requestData['bAddress1']
        bAddress2 = requestData['bAddress2']
        bCity = requestData['bCity']
        bState = requestData['bState']
        bZip = requestData['bZip']
        
        try:
            with connection.cursor() as cursor:
                query = 'SELECT * FROM billing_account WHERE BAccount_name = %s'
                cursor.execute(query, (bacctName))
                if cursor.fetchone():
                    error = "%s is already taken." % (bacctName)
                    return render_template('billing.html', error=error)
                query = 'INSERT INTO billing_account (BAccount_name, BAccount_name2, Baddress1, Baddress2, BCity, BState, BZip) VALUES (%s, %s, %s, %s, %s, %s, %s)'
                cursor.execute(query, (bacctName, bacctName2, bAddress1, bAddress2, bCity, bState, bZip))
                query = 'INSERT INTO member_billing (Username, BAccount_name) VALUES (%s, %s)'
                cursor.execute(query, (session['username'], bacctName))
                
        except pymysql.err.IntegrityError:
            error = 'Error.'
            return render_template('billing.html', error=error)

        return redirect(url_for('billing'))

    error = "An error has occurred. Please try again."
    return render_template("billing.html", error=error)

@app.route('/contract')
@login_required
def contract():
    with connection.cursor() as cursor:
        query = 'SELECT c.Contract_number, c.Life_of_business, c.Series_name, c.Plan_name \
                    FROM contract c, has_contract hc, acct_member am WHERE am.username = %s AND \
                        am.SSN = hc.SSN AND c.Contract_number = hc.Contract_number'
        cursor.execute(query, (session['username']))
    data = cursor.fetchall()
    return render_template('contract.html', data=data)

@app.route('/addContract', methods=['post'])
@login_required
def addContract():
    if request.form:
        requestData = request.form
        contractNumber = requestData['contractNumber']
        lifeOfBusiness = requestData['lifeOfBusiness']
        seriesName = requestData['seriesName']
        planName = requestData['planName']
        
        try:
            with connection.cursor() as cursor:
                query = 'SELECT * FROM contract WHERE Contract_number = %s'
                cursor.execute(query, (contractNumber))
                if cursor.fetchone():
                    error = "%s is already taken." % (contractNumber)
                    return render_template('contract.html', error=error)
                query = 'INSERT INTO contract (Contract_number, Life_of_business, Series_name, Plan_name) VALUES (%s, %s, %s, %s)'
                cursor.execute(query, (contractNumber, lifeOfBusiness, seriesName, planName))
                query = 'SELECT * FROM acct_member WHERE username = %s'
                cursor.execute(query, (session['username']))
                dt = cursor.fetchone()
                ssn = dt['SSN']
                query = 'INSERT INTO has_contract (SSN, Contract_number) VALUES (%s, %s)'
                cursor.execute(query, (ssn, contractNumber))
                
        except pymysql.err.IntegrityError:
            error = 'Error.'
            return render_template('contract.html', error=error)

        return redirect(url_for('contract'))

    error = "An error has occurred. Please try again."
    return render_template("billing.html", error=error)