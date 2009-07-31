"""
<Program>
  lockserver_daemon.py

<Started>
  30 June 2009

<Author>
  Justin Samuel

<Purpose>
  This is the XML-RPC Backend that is used by various components of
  SeattleGeni.
 

XML-RPC Interface:
 
 TODO: describe the interface
"""

import sys
import time
import traceback

# TODO: remove this and use starttimer after #548 is resolved.
import thread

# These are used to build a single-threaded XMLRPC server.
import SocketServer
import SimpleXMLRPCServer


from seattlegeni.common.api import keydb
from seattlegeni.common.api import keygen
# The lockserver is needed by the vessel cleanup thread.
from seattlegeni.common.api import lockserver
from seattlegeni.common.api import maindb
from seattlegeni.common.api import nodemanager

from seattlegeni.common.exceptions import *

from seattlegeni.common.util import log

from seattlegeni.common.util.assertions import *

from seattlegeni.common.util.decorators import log_function_call


# The port that we'll listen on.
LISTENPORT = 8020





class ThreadedXMLRPCServer(SocketServer.ThreadingMixIn, SimpleXMLRPCServer.SimpleXMLRPCServer):
  """This is a threaded XMLRPC Server. """
  




def _get_node_handle_from_nodeid(nodeid):
  
  # Raises DoesNotExistError if no such node exists.
  node = maindb.get_node(nodeid)
  # Raises DoesNotExistError if no such key exists.  
  owner_privkey = keydb.get_private_key(node.owner_pubkey)
  
  return nodemanager.get_node_handle(nodeid, node.last_known_ip, node.last_known_port, node.owner_pubkey, owner_privkey)

    



def _assert_number_of_arguments(functionname, args, exact_number):
  """
  <Purpose>
    Ensure that an args tuple which one of the public xmlrpc functions was
    called with has an expected number of arguments.
  <Arguments>
    functionname:
      The name of the function whose number of arguments are being checked.
      This is just for logging in the case that the arguments don't match.
    args:
      A tuple of arguments (received by the other function through *args).
    exact_number:
      The exact number of arguments that must be in the args tuple.
  <Exceptions>
    Raises InvalidRequestError if args does not contain exact_number
    items.
  <Side Effects>
    None.
  <Returns>
    None.
  """
  if len(args) != exact_number:
    message = "Invalid number of arguments to function " + functionname + ". "
    message += "Expected " + str(exact_number) + ", received " + str(len(args)) + "."
    raise InvalidRequestError(message)





class BackendPublicFunctions(object):
  """
  All public functions of this class are automatically exposed as part of the
  xmlrpc interface.
  """
  
  def _dispatch(self, method, args):
    """
    We provide a _dispatch function (which SimpleXMLRPCServer looks for and
    uses) so that we can log exceptions due to our programming errors within
    the backend as well to detect incorrect usage by clients.
    """
      
    try:
      # Set a unique request id for this thread for log messages.
      log.set_request_id()

      # Get the requested function (making sure it exists).
      try:
        func = getattr(self, method)
      except AttributeError:
        raise InvalidRequestError("The requested method '" + method + "' doesn't exist.")
      
      # Call the requested function.
      return func(*args)
    
    except (InvalidRequestError, AssertionError):
      log.error("The backend was used incorrectly: " + traceback.format_exc())
      raise
    
    except:
      # We assume all other exceptions are bugs in the backend. Unlike the
      # lockserver where it might result in broader data corruption, here in
      # the backend we allow the backend to continue serving other requests.
      
      # TODO: this should probably send an email or otherwise make noise.
      log.critical("The backend had an internal error: " + traceback.format_exc())
      




  # Using @staticmethod makes it so that 'self' doesn't get passed in as the first arg.
  @staticmethod
  @log_function_call
  def GenerateKey(*args):
    """
    This is a public function of the XMLRPC server. See the module comments at
    the top of the file for a description of how it is used.
    """
    _assert_number_of_arguments('GenerateKey', args, 1)
    
    keydescription = args[0]
    
    assert_str(keydescription)
    
    # Generate a new keypair.
    (pubkey, privkey) = keygen.generate_keypair()
    
    # Store the private key in the keydb.
    keydb.set_private_key(pubkey, privkey, keydescription)
    
    # Return the public key.
    return pubkey



  # Using @staticmethod makes it so that 'self' doesn't get passed in as the first arg.
  @staticmethod
  @log_function_call
  def SetVesselUsers(*args):
    """
    This is a public function of the XMLRPC server. See the module comments at
    the top of the file for a description of how it is used.
    """
    _assert_number_of_arguments('SetVesselUsers', args, 3)
    (nodeid, vesselname, userkeylist) = args
    
    assert_str(nodeid)
    assert_str(vesselname)
    assert_list(userkeylist)
    
    for userkey in userkeylist:
      assert_str(userkey)

    # Note: The nodemanager checks whether each key is a valid key and will
    #       raise an exception if it is not.
      
    # Raises a DoesNotExistError if there is no node with this nodeid.
    nodehandle = _get_node_handle_from_nodeid(nodeid)
    
    # Raises NodemanagerCommunicationError if it fails.
    nodemanager.change_users(nodehandle, vesselname, userkeylist)





  # Using @staticmethod makes it so that 'self' doesn't get passed in as the first arg.
  @staticmethod
  @log_function_call
  def SetVesselOwner(*args):
    """
    This is a public function of the XMLRPC server. See the module comments at
    the top of the file for a description of how it is used.
    """
    _assert_number_of_arguments('SetVesselOwner', args, 4)
    (authcode, nodeid, vesselname, ownerkey) = args
    
    assert_str(authcode)
    assert_str(nodeid)
    assert_str(vesselname)
    assert_str(ownerkey)
    
    # Note: The nodemanager checks whether the owner key is a valid key and
    #       will raise an exception if it is not.
    
    # Raises a DoesNotExistError if there is no node with this nodeid.
    nodehandle = _get_node_handle_from_nodeid(nodeid)
    
    # Raises NodemanagerCommunicationError if it fails.
    nodemanager.change_owner(nodehandle, vesselname, ownerkey)
    
    
    
 
    
  # Using @staticmethod makes it so that 'self' doesn't get passed in as the first arg.
  @staticmethod
  @log_function_call
  def SplitVessel(*args):
    """
    This is a public function of the XMLRPC server. See the module comments at
    the top of the file for a description of how it is used.
    """
    _assert_number_of_arguments('SplitVessels', args, 4)
    (authcode, nodeid, vesselname, desiredresourcedata) = args
    
    assert_str(authcode)
    assert_str(nodeid)
    assert_str(vesselname)
    assert_str(desiredresourcedata)
    
    # Raises a DoesNotExistError if there is no node with this nodeid.
    nodehandle = _get_node_handle_from_nodeid(nodeid)
    
    # Raises NodemanagerCommunicationError if it fails.
    nodemanager.split_vessel(nodehandle, vesselname, desiredresourcedata)
    
    



  # Using @staticmethod makes it so that 'self' doesn't get passed in as the first arg.
  @staticmethod
  @log_function_call
  def JoinVessels(*args):
    """
    This is a public function of the XMLRPC server. See the module comments at
    the top of the file for a description of how it is used.
    """
    _assert_number_of_arguments('JoinVessels', args, 4)
    (authcode, nodeid, firstvesselname, secondvesselname) = args
    
    assert_str(authcode)
    assert_str(nodeid)
    assert_str(firstvesselname)
    assert_str(secondvesselname)
    
    # Raises a DoesNotExistError if there is no node with this nodeid.
    nodehandle = _get_node_handle_from_nodeid(nodeid)
    
    # Raises NodemanagerCommunicationError if it fails.
    nodemanager.join_vessels(nodehandle, firstvesselname, secondvesselname)
      




def cleanup_vessels():
  
  # This thread will never end this lockserver session.
  lockserver_handle = lockserver.create_lockserver_handle()

  # Run forever.
  while True:
    
    try:
      # First, make it so that expired vessels are seen as dirty.
      markedcount = maindb.mark_expired_vessels_as_dirty()
      log.info("[cleanup_vessels] " + str(markedcount) + " expired vessels have been marked as dirty.")

      # Get a list of vessels to clean up. This doesn't include nodes known to
      # be inactive as we would just continue failing to communicate with nodes
      # that are down.
      cleanupvessellist = maindb.get_vessels_needing_cleanup()
      log.info("[cleanup_vessels] " + str(len(cleanupvessellist)) + " vessels to clean up.")
      
      # Now go through all of the dirty vessels and clean them up.
      for vessel in cleanupvessellist:
        
        nodeid = maindb.get_node_identifier_from_vessel(vessel)
        
        lockserver.lock_node(lockserver_handle, nodeid)
        try:
          # Now that we have a lock on the node that this vessel is on, find out
          # if we should still clean up this vessel (e.g. maybe a node state
          # transition script moved the node to a new state and this vessel was
          # removed).
          needscleanup, reasonwhynot = maindb.does_vessel_need_cleanup(vessel)
          if not needscleanup:
            log.info("[cleanup_vessels] Vessel " + str(vessel) + " no longer needs cleanup: " + reasonwhynot)
            continue
          
          # Raises a DoesNotExistError if there is no node with this nodeid.
          nodehandle = _get_node_handle_from_nodeid(nodeid)
          
          log.info("[cleanup_vessels] About to ChangeUsers on vessel " + str(vessel))
          nodemanager.change_users(nodehandle, vessel.name, [''])
          
          log.info("[cleanup_vessels] About to ResetVessel on vessel " + str(vessel))
          nodemanager.reset_vessel(nodehandle, vessel.name)
          
          # We only mark it as clean if no exception was raised when trying to
          # perform the above nodemanager operations.
          maindb.mark_vessel_as_clean(vessel)

          log.info("[cleanup_vessels] Successfully cleaned up vessel " + str(vessel))
          
        except NodemanagerCommunicationError:
          log.info("[cleanup_vessels] Failed to cleanup vessel " + str(vessel) + ". " + traceback.format_exc())
          
        finally:
          # Always unlock the node.
          lockserver.unlock_node(lockserver_handle, nodeid)
        
    except:
      # TODO: should send email or otherwise make noise to alert developers
      log.critical("[cleanup_vessels] Something very bad happened: " + traceback.format_exc())

    # Sleep a few seconds for those times where we don't have any vessels to clean up.
    time.sleep(5)





def main():
  
  # Initialize the main database.
  maindb.init_maindb()

  # Initialize the key database.
  keydb.init_keydb()

  # Start the background thread that does vessel cleanup.
  # TODO: change this to use starttimer after #548 is resolved.
  thread.start_new_thread(cleanup_vessels, ())

  # Register the XMLRPCServer. Use allow_none to allow allow the python None value.
  server = ThreadedXMLRPCServer(("127.0.0.1", LISTENPORT), allow_none=True)

  log.info("Backend listening on port " + str(LISTENPORT) + ".")

  server.register_instance(BackendPublicFunctions()) 
  while True:
    server.handle_request()





if __name__ == '__main__':
  try:
    main()
  except KeyboardInterrupt:
    log.info("Exiting on KeyboardInterrupt.")
    sys.exit(0)