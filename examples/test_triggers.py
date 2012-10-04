
# Go two levels up and add that directory to the PATH, so we can find zync.py.
import sys, os
sys.path.append( os.path.dirname( os.path.dirname( os.path.abspath(__file__) ) ) )

# Import ZYNC Python API.
import zync

# Connect to ZYNC. Set up a script & API token via the Admin page in the ZYNC
# Web Console.
z = zync.Zync( "SCRIPT_NAME", "API_TOKEN" )

# Get a list of all unseen trigger events.
event_list = z.get_triggers()

# Display each completed job.
for event in event_list:
    if event["event_type"] == "job_complete":
        print "Job %s Completed!" % ( event["job_id"], )
