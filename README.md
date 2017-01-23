# Description

See comments and explanations in `example_stereo.xml` or `example_terminal.xml`.

These files contain a list of binaries, the component repository and an abstract (i.e. platform- and implementation-independent) system configuration.

# Model checking

The script `ConfigModelChecker.py` takes an XML file as input and performs the following:

* Checks the XML structure (nodes, required/optional attributes, etc.).
* Checks ambiguity of function and component names.
* Checks ambiguity of component classification.
* Checks availability of referenced names.
* Tries to transform the abstract configuration into an actual system configuration.

# Known issues/limitations

Model:

* There is currently no way to describe a mapping between a function provided
  by a component and the service(s) by which this function can be accessed. This
  is intentional because it simplifies the specification and we expect that there
  are only rare cases where this would be actually necessary. More precisely, those
  cases, for which the service-level routes must be specified explicitly in the abstract
  configuration, could be:
  
  * A component with two function requirements that are routed to different providers
    that both provide the service interfaces required by the component. In this case,
	 it is not ensured that the services are connected to the correct provider.
  * A component with one function requirement and multiple service requirements of the 
    same type.
  * A component connecting to a function provider that provides multiple services of
    which none matches the only service requirement. In this case, a protocol stack
	 must be inserted. However, it is not ensured that this connects the service 
	 requirement to the wrong service interface of the function provider.

  The reason not to address this limitation for the moment is that specifying the
  mapping between functions and services explicitly significantly reduces readability:

      <provides>
		  <!-- option 1 (easy to parse by flattening the hierachry) //-->
		  <function name="FOOBAR">
		    <service name="foo" />
		    <service name="bar" />
		  </function>

		  <!-- option 2 (parser must ignore duplicate functions) //-->
		  <service name="foo"> <function name="FOOBAR" /> </service>
		  <service name="bar"> <function name="FOOBAR" /> </service>
	   </provides>
      <requires>
		  <!-- option 1 (is in contrast to routing syntax; for composites there can be multiple service connections) //-->
		  <function name="FOOBAR">
		    <service name="foo" />
		    <service name="bar" />
		  </function>

		  <!-- option 2 (matches routing syntax) //-->
		  <service name="foo"> <function name="FOOBAR" /> </service>
		  <service name="bar"> <function name="FOOBAR" /> </service>
      </requires>