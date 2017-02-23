"""`main` is the top level module for your Flask application."""

# Mobile Byte Version 1
# 
# Copyright 1/2016 Jennifer Mankoff
#
# Licensed under GPL v3 (http://www.gnu.org/licenses/gpl.html)
#

# Imports
import os
import jinja2
import webapp2
import logging
import json
import urllib
import MySQLdb
import math

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

# Define your production Cloud SQL instance information.
_INSTANCE_NAME = 'ren-rides:us-east1:lrenaud'
_DB_NAME = 'awaredata'
_USER = 'lrenaud' # or whatever other user account you created
_PSWD = 'renaudCMU27'

# the table where activities are logged
_ACTIVITY = 'plugin_google_activity_recognition'
# the table where locations are logged
_TABLE = 'screen'
# the distance that determins new locations
_EPSILON = 1

# Import the Flask Framework
from flask import Flask, request
app = Flask(__name__)

# Note: We don't need to call run() since our application is embedded within
# the App Engine WSGI application server.

@app.route('/')
def index():
    template = JINJA_ENVIRONMENT.get_template('templates/index.html')
    
    if (os.getenv('SERVER_SOFTWARE') and
        os.getenv('SERVER_SOFTWARE').startswith('Google App Engine/')):
        db = MySQLdb.connect(unix_socket='/cloudsql/' + _INSTANCE_NAME,
                             db=_DB_NAME, user=_USER, passwd=_PSWD, charset='utf8')
        cursor = db.cursor()
        
        logging.info("making queries")
        
        query = "SELECT CONVERT_TZ(FROM_UNIXTIME(timestamp/1000, '%Y-%m-%d %H:%i'), 'GMT', 'EST') as screen_time, (HOUR(CONVERT_TZ((FROM_UNIXTIME(timestamp/1000)), 'GMT', 'EST'))) as hour, screen_status FROM screen;"
        
        rows = make_query(cursor, query)
        queries = [{"query": query, "results": rows}]
        
        ## tried to get it to work with two queries,
        ## but couldn't figure out how to call one of them but not both of them
        #rows_screen =  = make_query(cursor, query_screen)
        #query_screen = "SELECT CONVERT_TZ(FROM_UNIXTIME(timestamp/1000, '%Y-%m-%d %H:%i'), 'GMT', 'EST') as screen_time, (HOUR(CONVERT_TZ((FROM_UNIXTIME(timestamp/1000)), 'GMT', 'EST'))) as hour, screen_status FROM screen;"
        #rows_charging =  = make_query(cursor, query_charging)
        #query_charging = "SELECT CONVERT_TZ(FROM_UNIXTIME(timestamp/1000, '%Y-%m-%d %H:%i'), 'GMT', 'EST') as start_charge, CONVERT_TZ(FROM_UNIXTIME(double_end_timestamp/1000, '%Y-%m-%d %H:%i'), 'GMT', 'EST') as end_charge, (HOUR(CONVERT_TZ((FROM_UNIXTIME(timestamp/1000)), 'GMT', 'EST'))) as start_hour, round((double_end_timestamp - timestamp)/1000/60,0) as minutes_charging FROM battery_charges;"
        #queries = [{"query_screen": query_screen, "results": rows_screen, 
        #            "query_charging": query_charging, "results": rows_charging}]
        
        
            
    else:
        queries = [{"query": 'Need to connect from Google Appspot', "results": []}]

    logging.info(queries)
    
    context = {"queries": queries}
    
    return template.render(context)

    
@app.route('/about')
def about():
    template = JINJA_ENVIRONMENT.get_template('templates/about.html')
    return template.render()

@app.route('/quality')
def quality():
    template = JINJA_ENVIRONMENT.get_template('templates/quality.html')
    return template.render()

@app.errorhandler(404)
def page_not_found(e):
    """Return a custom 404 error."""
    return 'Sorry, Nothing at this URL.', 404

@app.errorhandler(500)
def application_error(e):
    """Return a custom 500 error."""
    return 'Sorry, unexpected error: {}'.format(e), 500

# Takes the database link and the query as input
def make_query(cursor, query):
    # this is for debugging -- comment it out for speed
    # once everything is working

    try:
        # try to run the query
        cursor.execute(query)
        # and return the results
        return cursor.fetchall()
    
    except Exception:
        # if the query failed, log that fact
        logging.info("query making failed")
        logging.info(query)

        # finally, return an empty list of rows 
        return []

# helper function to make a query and print lots of 
# information about it. 
def make_and_print_query(cursor, query, description):
    logging.info(description)
    logging.info(query)
    
    rows = make_query(cursor, query)
        
def bin_locations(locations, epsilon):
    # always add the first location to the bin
    bins = {1: [locations[0][0], locations[0][1]]}
    # this gives us the current maximum key used in our dictionary
    num_places = 1
    
    # now loop through all the locations 
    for location in locations:
        lat = location[0]
        lon = location[1]
        # assume that our current location is new for now (hasn't been found yet)
        place_found = False
        # loop through the bins 
        for place in bins.values():
            # check whether the distance is smaller than epsilon
            if distance_on_unit_sphere(lat, lon, place[0], place[1]) < epsilon:
                #(lat, lon) is near  (place[0], place[1]), so we can stop looping
                place_found = True
                    
        # we weren't near any of the places already in bins
        if place_found is False:
            logging.info("new place: {0}, {1}".format(lat, lon))
            # increment the number of places found and create a new entry in the 
            # dictionary for this place. Store the lat lon for comparison in the 
            # next round of the loop
            num_places = num_places + 1
            bins[num_places] = [lat, lon]

    return bins.values()
            
def find_bin(bins, lat, lon, epsilon):
    for i in range(len(bins)):
        blat = bins[i][0]
        blon = bins[i][1]
        if distance_on_unit_sphere(lat, lon, blat, blon) < epsilon:
            return i
    bins.append([lat, lon])
    return len(bins)-1

def group_activities_by_location(bins, locations, activities, epsilon):
    searchable_locations = {}
    for location in locations:
        # day, hour
        key = (location[0], location[1])
        if key in searchable_locations:
            # lat,   lon 
            searchable_locations[key] = locations[key] + [(location[2], location[3])]
        else:
            searchable_locations[key] = [(location[2], location[3])]
    
    # a place to store activities for which we couldn't find a location
    # (indicates an error in either our data or algorithm)
    no_loc = []
    for activity in activities:
        # collect the information we will need 
        aday = activity[0] # day
        ahour = activity[1] # hour
        aname = activity[2] # name
        logging.info(aday + aname)
        try: 
            possible_locations = searchable_locations[(aday, ahour)]
            # loop through the locations
            for location in possible_locations:
                logging.info(" about to find bin")
                bin = find_bin(bins, location[0], location[1], epsilon)
                # and add the information to it
                bins[bin] = bins[bin] + [aname]
        except KeyError:
            no_loc.append([aname])

    # add no_loc to the bins
    bins.append(no_loc)
    # this function is taken verbatim from http://www.johndcook.com/python_longitude_latitude.html

def distance_on_unit_sphere(lat1, long1, lat2, long2):

    # Convert latitude and longitude to 
    # spherical coordinates in radians.
    degrees_to_radians = math.pi/180.0
    
    # phi = 90 - latitude
    phi1 = (90.0 - lat1)*degrees_to_radians
    phi2 = (90.0 - lat2)*degrees_to_radians
    
    # theta = longitude
    theta1 = long1*degrees_to_radians
    theta2 = long2*degrees_to_radians
    
    # Compute spherical distance from spherical coordinates.
    
    # For two locations in spherical coordinates 
    # (1, theta, phi) and (1, theta, phi)
    # cosine( arc length ) = 
    #    sin phi sin phi' cos(theta-theta') + cos phi cos phi'
    # distance = rho * arc length
        
    cos = (math.sin(phi1)*math.sin(phi2)*math.cos(theta1 - theta2) + 
           math.cos(phi1)*math.cos(phi2))
    # sometimes small errors add up, and acos will fail if cos > 1
    if cos>1: cos = 1
    arc = math.acos( cos )
    
    # Remember to multiply arc by the radius of the earth 
    # in your favorite set of units to get length.
    return arc