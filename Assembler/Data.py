#! /usr/bin/python3

from sys        import exit
from Utility    import Utility
from Debug      import Debug

class Variable (Debug, Utility):
    """Describes a variable and what we know about it so far"""

    def parse_value (self, label, initial_values):
        """Deal with ints, lists, and strings. Convert to int where possible."""
        if type(initial_values) == list:
            if len(initial_values) == 0:
                print("Empty list of values passed to variable {0}.".format(label))
                exit(1)
            if len(initial_values) > 1:
                initial_values = [self.try_int(entry) for entry in initial_values]
            else:
                initial_values = self.try_int(initial_values[0])
        elif type(initial_values) == str:
            initial_values = self.try_int(initial_values)
        elif type(initial_values) == int:
            pass
        elif type(initial_values) == type(None):
            pass
        else:
            print("Unusable initial value {0} for variable {1}".format(label, initial_values))
            exit(1)
        return initial_values

    def __init__ (self, label = None, address = None, value = None, memory = None):
        Debug.__init__(self)
        self.label   = label
        self.address = address
        self.value   = self.parse_value(label, value)
        self.memory  = memory

class Pointer (Variable):
    """Describes pointer initialization data and which indirect memory slot it refers to"""

    def __init__ (self, label = None, address = None, value = None, memory = None, read_base = None, read_incr = None, write_base = None, write_incr = None, slot = None):
        Variable.__init__(self, label = label, address = address, value = value, memory = memory)
        self.read_base  = read_base
        self.read_incr  = read_incr
        self.write_base = write_base
        self.write_incr = write_incr
        self.slot       = slot
        # Set at Resolution, as the code and data haven't been generated yet!
        self.init_load  = None

class Port (Variable):
    """Describes an I/O port. Derive address from port number. Has no value (set to 0)."""

    def __init__ (self, label = None, address = None, memory = None, number = None):
        Variable.__init__(self, label = label, address = address, value = 0, memory = memory)
        self.number = number

class Data (Utility, Debug):
    """Contains descriptions of data and resolves locations, etc... before passing to back-end for memory image generation"""

    def __init__ (self, configuration):
        Utility.__init__(self)
        Debug.__init__(self)
        self.current_threads = []
        # Variable types
        self.shared     = []
        self.private    = []
        self.pointers   = []
        self.ports      = []
        self.variables  = [self.shared, self.private, self.pointers, self.ports]
        self.configuration = configuration
        # Location Zero is a special case always equal to zero.
        # It must exist before any other shared variable.
        self.shared.append(Variable(label = None, address = 0, value = 0, memory = "A"))
        self.shared.append(Variable(label = None, address = 0, value = 0, memory = "B"))

    def __str__ (self):
        output = "\nData:\n"
        output += "\nCurrent Threads: " + str(self.current_threads) + "\n"  
        output += "\nPrivate Variables:\n"
        output += self.list_str(self.private)
        output += "\nShared Variables:\n"
        output += self.list_str(self.shared) + "\n"
        output += self.list_str(self.pointers) + "\n"
        output += self.list_str(self.ports) + "\n"
        return output

    def set_current_threads (self, thread_list):
        self.current_threads = [self.try_int(thread) for thread in thread_list]
        # Type check
        for thread in self.current_threads:
            if type(thread) is not int:
                print("Thread values must be literal integers: {0}".format(self.current_threads))
                exit(1)
        # Range check
        min_thread = 0
        max_thread = self.configuration.thread_count - 1
        for thread in self.current_threads:
            if thread < min_thread or thread > max_thread:
                print("Out of range thread: {0}. Min: {1}, Max: {2}".format(self.thread, min_thread, max_thread))
                exit(1)
        # Duplication test
        if len(self.current_threads) > len(set(self.current_threads)):
            print("Duplicate thread numbers not allowed: {0}".format(current_threads))
            exit(1)

    def lookup_variable_type (self, variable):
        """Searches the variable type lists to find the one the given variable belongs to."""
        for variable_type in self.variables:
            if variable in variable_type:
                return variable_type
        # A variable not in a type list, or a non-existent variable, should never happen.
        print("Variable {0} does not belong to any type! This is impossible.".format(variable.label))
        exit(1)

    def lookup_variable_name (self, name, specific_variable_type = None):
        """Locate variable by name if it exists.
           Specify variable type list if you want to lookup a specific type.
           Return list of variables of that name across all threads."""
        if name is None:
            print("Variable name lookup cannot have a None name!")
            exit(1)
        variable_types  = []
        variables       = []
        for variable_type in self.variables:
            for variable in variable_type:
                if variable.label == name:
                    variable_types.append(variable_type)
                    variables.append(variable)
        if len(variables) == 0:
            return None
        # Now check that the variable does not exist in multiple types, which is an error.
        # Just pick one type and compare it to the rest.
        test_type = variable_types[0]
        for variable_type in variable_types:
            if variable_type != test_type:
                print("Variable name {0} found in two variable types {1} and {2}.".format(name, test_type, variable_type))
                exit(1)
        # If a desired variable type was given, check that the found variables are in that type.
        if specific_variable_type is not None and test_type != specific_variable_type:
            print("Variable name {0} found in variable type {1}, not in specified variable type {2}.".format(name, test_type, specific_variable_type))
            exit(1)
        return variables

    def lookup_shared_variable_value (self, value, memory):
        """Locate unnamed shared variable by value if it exists in the given memory.
           Search exhaustively for duplicates, which should not exist within a memory.
           (Value duplicates across memories are OK.)"""
        variables = []
        for variable in self.shared:
            if variable.label == None and variable.value == value and variable.memory == memory:
                variables.append(variable)
        if len(variables) == 0:
            return None
        if len(variables) > 1:
            print("Unnamed shared variable of value {0} found more than once in memory {1}.".format(value, memory))
            exit(1)
        return variables[0]

    def allocate_private (self, label, initial_values = None):
        """Allocate a private variable. Must be named (label not None)."""
        if label is None:
            print("Private variable label/name cannot be None! Initial value: {0}".format(initial_values))
            exit(1)
        variable = Variable(label = label, value = initial_values, threads = self.current_threads)
        self.private.append(variable)
        return variable

    def allocate_shared (self, label, initial_values = None):
        """Allocate a shared variable."""
        variable = Variable(label = label, value = initial_values)
        self.shared.append(variable)
        return variable

    def next_pointer_slot (self, set_pointer):
        """Find the highest used slot in all pointers in the same memory, and return the next one."""
        max_slot = -1
        for pointer in self.pointers:
            if pointer.memory != set_pointer.memory:
                continue
            slot     = pointer.slot
            if slot is None:
                slot = -1
            max_slot = max(slot, max_slot)
        return max_slot + 1

    def allocate_pointer (self, label, read_base = None, read_incr = None, write_base = None, write_incr = None):
        # We can't determine the init data value until we know which Data Memory it's read from.
        # This also affects the placement of the referred-to pointer/array.
        # The bases are labels until resolved to addresses
        if label is None:
            print("Pointer cannot have a None name! Read/Write bases: {0}, {1}".format(read_base, write_base))
            exit(1)
        read_incr   = self.try_int(read_incr)
        write_incr  = self.try_int(write_incr)
        new_pointer = Pointer(label = label, read_base = read_base, read_incr = read_incr, write_base = write_base, write_incr = write_incr)
        # Can't set slot here, as we don't know which Data Memory we will end up in. This is done at Resolution.
        self.pointers.append(new_pointer)
        return new_pointer

    def allocate_port (self, label, memory, number):
        if label is None:
            print("Port cannot have a None name! Memory: {0}, Number: {1}".format(memory, number))
            exit(1)
        number      = int(number, 0)
        new_port    = Port(label = label, number = number, memory = memory)
        self.ports.append(new_port)
        return new_port

    def next_variable_address (self, variables, memory):
        # No variable created at address zero. (Zero Register)
        # Add the length of the data of the max-addressed variable
        # so we return the next address just past its value(s)
        # Find in the same memory only, of course
        max_address     = 0
        max_data_length = 1
        #
        # Find the higest set address for the given variable type in the given memory
        for variable in variables:
            address = variable.address
            if address is not None and variable.memory == memory:
                if address > max_address:
                    max_address     = address
                    if type(variable.value) == list:
                        max_data_length = len(variable.value)
                    else:
                        max_data_length = 1
        next_address =  max_address + max_data_length
        #
        # Limit the address to the given range of the variables (shared, private, etc...)
        # We assume shared starts at zero
        if variables == self.shared and next_address not in self.configuration.memory_map.shared:
            print("Out of bounds address {0} for shared variable. Limit is {1}.".format(next_address, self.configuration.memory_map.shared[-1]))
            exit(1)
        #
        if variables == self.private and next_address not in self.configuration.memory_map.private:
            # Catch the first private variable and put it at the start of the private area, the rest will follow.
            if next_address < self.configuration.memory_map.private[0]:
                next_address = self.configuration.memory_map.private[0]
            else:
                # Then it's greater...
                print("Out of bounds address {0} for private variable. Limit is {1}".format(next_address, self.configuration.memory_map.private[-1]))
                exit(1)
        #
        return next_address

    def resolve_shared_value (self, value, memory):
        variable = self.lookup_shared_variable_value(value, memory)
        # Is it in the memory we specified?
        # If not, create it!
        if variable is None:
            variable = self.allocate_shared(None, initial_values = value)
            variable.memory = memory
        if variable.address is None:
            variable.address = self.next_variable_address(self.shared, memory)
        return variable

    def resolve_named (self, name, memory):
        """Lookup a variable and allocate it an address and a memory if not already set.
           For private variables existing in multiple threads, allocate the first one found,
           then apply the same memory and address to all the others of the same name.
           Returns the first matched variable, as its identical to the others, except for assigned thread."""

        # We know that the list is always of variables of a single type
        variables = self.lookup_variable_name(name)

        if variables is None:
            print("Unknown variable name {0}".format(name))
            exit(1)

        # Use the first match for sanity checks and for resolution.
        variable = variables[0]

        if variable in self.shared:
            if len(variables) > 1:
                print("Duplicate shared variable {0}: {1}".format(variable.label, variables))
                exit(1)
            if variable.address is None:
                variable.address = self.next_variable_address(self.shared, memory)
            if variable.memory is not None and variable.memory != memory:
                print("Conflicting memory allocation for shared variable {0}. Was {1}, now {2}".format(name, variable.memory, memory))
                exit(1)
            variable.memory = memory 
            return variable

        if variable in self.private:
            if variable.address is None:
                variable.address = self.next_variable_address(self.private, memory)
            if variable.memory is not None and variable.memory != memory:
                print("Conflicting memory allocation for private variable {0}. Was {1}, now {2}".format(name, variable.memory, memory))
                exit(1)
            variable.memory = memory 
            # Now apply to all the other thread instances of that variable
            for instance in variables:
                instance.address = variable.address
                instance.memory  = variable.memory
            return variable

        # Ports are located in the shared address space, so treat them like shared variables.
        if variable in self.ports:
            if len(variables) > 1:
                print("Duplicate port variable {0}: {1}".format(variable.label, variables))
                exit(1)
            if variable.address is None:
                variable.address = self.configuration.memory_map.io[variable.number]
            # Memory always set at port definition
            if variable.memory != memory:
                print("Conflicting memory allocation for I/O port {0}. Was {1}, now {2}".format(name, variable.memory, memory))
                exit(1)
            return variable

        # Pointers are located in the shared address space, but are initialized per-thread.
        if variable in self.pointers:
            if variable.memory is not None and variable.memory != memory:
                print("Conflicting memory allocation for pointer {0}. Was {1}, now {2}".format(name, variable.memory, memory))
                exit(1)
            variable.memory = memory 
            if variable.slot is None:
                variable.slot = self.next_pointer_slot(variable)
            if variable.address is None:
                variable.address = self.configuration.memory_map.indirect[variable.slot]
            # Now apply to all the other thread instances of that pointer
            for instance in variables:
                instance.slot    = variable.slot
                instance.address = variable.address
                instance.memory  = variable.memory
            return variable


