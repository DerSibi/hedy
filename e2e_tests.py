import requests
import json
import random
from utils import type_check, timems
import urllib.parse
from config import config
import sys
import threading

host = 'http://localhost:' + str (config ['port']) + '/'
hosts = {'alpha': 'https://hedy-alpha.herokuapp.com/', 'test': 'https://hedy-test.herokuapp.com/'}

if len (sys.argv) == 3:
    if not sys.argv [2] in hosts:
        raise Exception ('No such host')
    host = hosts [sys.argv [2]]

# test structure: tag method path headers body code
def request(state, test, counter, username):

    start = timems ()

    if isinstance(threading.current_thread(), threading._MainThread):
        print ('Start #' + str (counter) + ': ' + test [0])

    # If no explicit cookie passed, use the one from the state
    if not 'cookie' in test [3] and 'cookie' in state ['headers']:
        test [3] ['cookie'] = state ['headers'] ['cookie']

    # If path, headers or body are functions, invoke them passing them the current state
    if type_check (test[2], 'fun'):
        test[2] = test[2] (state)

    if type_check (test[3], 'fun'):
        test[3] = test[3] (state)

    if type_check (test[4], 'fun'):
        test[4] = test[4] (state)

    if type_check (test[4], 'dict'):
        test[3] ['content-type'] = 'application/json'
        test[4] = json.dumps (test [4])
    r = getattr (requests, test [1]) (host + test [2], headers=test[3], data=test[4])

    if 'Content-Type' in r.headers and r.headers ['Content-Type'] == 'application/json':
        body = r.json ()
    else:
        body = r.text

    if r.history and r.history [0]:
        # This will be the case if there's a redirect
        code = r.history [0].status_code
    else:
        code = r.status_code

    output = {
        'code':    code,
        'headers': r.headers,
        'body':    body
    }

    if (code != test[5]):
        print (output)
        raise Exception ('A test failed!')

    if len (test) == 7:
        test [6] (state, output, username)

    if isinstance(threading.current_thread(), threading._MainThread):
        print ('Done  #' + str (counter) + ': ' + test [0] + ' - ' + str (r.status_code) + ' (' + str (timems () - start) + 'ms)')

    return output

def run_suite(suite):
    # We use a random username so that if a test fails, we don't have to do a cleaning of the DB so that the test suite can run again
    # This also allows us to run concurrent tests without having username conflicts.
    username = 'user' + str (random.randint (10000, 100000))
    tests = suite(username)
    state = {'headers': {}}
    t0 = timems ()

    if not type_check(tests, 'list'):
        return print ('Invalid test suite, must be a list.')
    counter = 1

    def run_test(test, counter):
        result = request(state, test, counter, username)

    for test in tests:
        # If test is nested, run a nested loop
        if not (type_check(test[0], 'str')):
            for subtest in test:
                run_test(subtest, counter)
                counter += 1
        else:
           run_test(test, counter)
           counter += 1

    if isinstance(threading.current_thread(), threading._MainThread):
        print ('Test suite successful! (' + str (timems () - t0) + 'ms)')
    else:
        return timems () - t0

def invalidMap(tag, method, path, bodies):
    output = []
    counter = 1
    for body in bodies:
        output.append (['invalid ' + tag + ' #' + str (counter), method, path, {}, body, 400])
        counter += 1
    return output

def successfulSignup(state, response, username):
    if not 'token' in response ['body']:
        raise Exception ('No token present')
    state ['token'] = response ['body'] ['token']

# We define apres functions here because multiline lambdas are not supported by python
def successfulLogin(state, response, username):
    state ['headers'] ['cookie'] = response ['headers'] ['Set-Cookie']

def getProfile1(state, response, username):
    profile = response ['body']
    if profile ['username'] != username:
        raise Exception ('Invalid username (getProfile1)')
    if profile ['email'] != username + '@e2e-testing.com':
        raise Exception ('Invalid username (getProfile1)')
    if not profile ['session_expires_at']:
        raise Exception ('No session_expires_at (getProfile1)')
    expire = profile ['session_expires_at'] - config ['session'] ['session_length'] * 60 * 1000 - timems ()
    if expire > 0:
        raise Exception ('Invalid session_expires_at (getProfile1), too large')
    # We give the server up to 2s to respond to the query
    if expire < -2000:
        raise Exception ('Invalid session_expires_at (getProfile1), too small')

def getProfile2(state, response, username):
    profile = response ['body']
    if profile ['country'] != 'NL':
        raise Exception ('Invalid country (getProfile2)')
    if profile ['email'] != username + '@e2e-testing2.com':
        raise Exception ('Invalid country (getProfile2)')
    if not 'verification_pending' in profile or profile ['verification_pending'] != True:
        raise Exception ('Invalid verification_pending (getProfile2)')

def getProfile3(state, response, username):
    profile = response ['body']
    if 'verification_pending' in profile:
        raise Exception ('Invalid verification_pending (getProfile3)')

def emailChange(state, response, username):
    if not type_check (response ['body'] ['token'], 'str'):
        raise Exception ('Invalid country (emailChange)')
    if response ['body'] ['username'] != username:
        raise Exception ('Invalid username (emailChange)')
    state ['token2'] = response ['body'] ['token']

def recoverPassword(state, response, username):
    if not 'token' in response ['body']:
        raise Exception ('No token present')
    state ['token'] = response ['body'] ['token']

def suite (username):
    return [
        ['get root', 'get', '/', {}, '', 200],
            invalidMap ('signup', 'post', '/auth/signup', ['', [], {}, {'username': 1}, {'username': 'user@me', 'password': 'foobar', 'email': 'a@a.com'}, {'username:': 'user: me', 'password': 'foobar', 'email': 'a@a.co'}, {'username': 't'}, {'username': '    t    '}, {'username': username}, {'username': username, 'password': 1}, {'username': username, 'password': 'foo'}, {'username': username, 'password': 'foobar'}, {'username': username, 'password': 'foobar', 'email': 'me@something'}]),
        ['valid signup', 'post', '/auth/signup', {}, {'username': username, 'password': 'foobar', 'email': username + '@e2e-testing.com'}, 200, successfulSignup],
        invalidMap ('login', 'post', '/auth/login', ['', [], {}, {'username': 1}, {'username': 'user@me'}, {'username:': 'user: me'}]),
        ['valid login, invalid credentials', 'post', '/auth/login', {}, {'username': username, 'password': 'password'}, 403],
        ['verify email (missing fields)', 'get', lambda state: '/auth/verify?' + urllib.parse.urlencode ({'username': 'foobar', 'token': state ['token']}), {}, '', 403],
        ['verify email (invalid username)', 'get', lambda state: '/auth/verify?' + urllib.parse.urlencode ({'username': 'foobar', 'token': state ['token']}), {}, '', 403],
        ['verify email (invalid token)', 'get', lambda state: '/auth/verify?' + urllib.parse.urlencode ({'username': username, 'token': 'foobar'}), {}, '', 403],
        ['verify email', 'get', lambda state: '/auth/verify?' + urllib.parse.urlencode ({'username': username, 'token': state ['token']}), {}, '', 302],
        ['valid login', 'post', '/auth/login', {}, {'username': username, 'password': 'foobar'}, 200, successfulLogin],
        invalidMap ('change password', 'post', '/auth/change_password', ['', [], {}, {'foo': 'bar'}, {'old_password': 1}, {'old_password': 'foobar'}, {'old_password': 'foobar', 'new_password': 1}, {'old_password': 'foobar', 'new_password': 'short'}]),
        ['change password', 'post', '/auth/change_password', {}, {'old_password': 'foobar', 'new_password': 'foobar2'}, 200],
        ['invalid login after password change', 'post', '/auth/login', {}, {'username': username, 'password': 'foobar'}, 403],
        ['valid login after password change', 'post', '/auth/login', {}, {'username': username + '@e2e-testing.com', 'password': 'foobar2'}, 200, successfulLogin],
        ['logout', 'post', '/auth/logout', {}, {}, 200],
        ['check that session is no longer valid', 'get', '/profile', {}, '', 403],
        ['login again', 'post', '/auth/login', {}, {'username': username, 'password': 'foobar2'}, 200, successfulLogin],
        invalidMap ('change password', 'post', '/auth/change_password', ['', [], {}, {'foo': 'bar'}, {'old_password': 1}, {'old_password': 'foobar'}, {'old_password': 'foobar', 'new_password': 1}]),
        ['get profile before profile update', 'get', '/profile', {}, {}, 200, getProfile1],
        invalidMap ('update profile', 'post', '/profile', ['', [], {'email': 'foobar'}, {'birth_year': 'a'}, {'birth_year': 20}, {'country': 'Netherlands'}, {'gender': 0}, {'gender': 'a'}]),
        ['change profile with same email', 'post', '/profile', {}, {'email': username + '@e2e-testing.com', 'country': 'US'}, 200],
        ['change profile with different email', 'post', '/profile', {}, {'email': username + '@e2e-testing2.com', 'country': 'NL'}, 200, emailChange],
        ['get profile after profile update', 'get', '/profile', {}, {}, 200, getProfile2],
        ['verify email after email change', 'get', lambda state: '/auth/verify?' + urllib.parse.urlencode ({'username': username, 'token': state ['token2']}), {}, '', 302],
        ['get profile after email verification', 'get', '/profile', {}, {}, 200, getProfile3],
        invalidMap ('recover password', 'post', '/auth/recover', ['', [], {}, {'username': 1}]),
        ['recover password, invalid user', 'post', '/auth/recover', {}, {'username': 'nosuch'}, 403],
        ['recover password', 'post', '/auth/recover', {}, {'username': username}, 200, recoverPassword],
        invalidMap ('reset password', 'post', '/auth/reset', ['', [], {}, {'username': 1}, {'username': 'foobar', 'token': 1}, {'username': 'foobar', 'token': 'some'}, {'username': 'foobar', 'token': 'some', 'password': 1}, {'username': 'foobar', 'token': 'some', 'password': 'short'}]),
        ['reset password, invalid username', 'post', '/auth/reset', {}, lambda state: {'username': 'foobar', 'token': state ['token'], 'password': 'foobar'}, 403],
        ['reset password, invalid token', 'post', '/auth/reset', {}, lambda state: {'username': username, 'token': 'foobar', 'password': 'foobar'}, 403],
        ['reset password, invalid password', 'post', '/auth/reset', {}, lambda state: {'username': username, 'token': state ['token'], 'password': 'short'}, 400],
        ['reset password', 'post', '/auth/reset', {}, lambda state: {'username': username, 'token': state ['token'], 'password': 'foobar3'}, 200],
        ['login again after reset', 'post', '/auth/login', {}, {'username': username, 'password': 'foobar3'}, 200],
        ['destroy account', 'post', '/auth/destroy', {}, {}, 200]
    ]

if len (sys.argv) == 1:
    run_suite (suite)
else:
    counter = 0
    threads = []
    results = []
    errors  = []

    def thread_function(counter):
        try:
            ms = run_suite (suite)
            print ('Finished concurrent test #' + str (counter))
            results.append (ms)
        except Exception as e:
            print ('Concurrent test #' + str (counter), "finished with error")
            errors.append (e)

    print ('Starting', sys.argv [1], 'concurrent tests')
    while counter < int (sys.argv [1]):
        counter += 1
        thread = threading.Thread (target=thread_function, args=[counter])
        thread.start ()
        threads.append (thread)

    for thread in threads:
        # join waits until all threads are done
        thread.join ()
    print ('Done with', sys.argv [1], 'concurrent tests,', len (results), 'OK,', len (errors), 'errors,', round (sum (results) / (len (results) * 1000), 2), 'seconds average')
