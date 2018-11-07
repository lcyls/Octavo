#! /usr/bin/python3

from sys        import exit
from Utility    import Utility
from Debug      import Debug

class Variable (Debug):
    """Describes a variable and what we know about it so far"""

    def __init__ (self, label = None, address = None, value = None, memory = None):
        Debug.__init__(self)
        self.label   = label
        self.address = address
        self.value   = value
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
        self.private    = []
        self.shared     = []
        # Location Zero is a special case always equal to zero.
        # It must exist before any other shared variable.
        self.shared.append(Variable(label = None, address = 0, value = [0], memory = "A"))
        self.shared.append(Variable(label = None, address = 0, value = [0], memory = "B"))
        self.pointers   = []
        self.ports      = []
        self.configuration = configuration

    def __str__ (self):
        output = "\nData:\n"
        output += "\nPrivate Variables:\n"
        output += self.list_str(self.private)
        output += "\nShared Variables:\n"
        output += self.list_str(self.shared) + "\n"
        output += self.list_str(self.pointers) + "\n"
        output += self.list_str(self.ports) + "\n"
        return output

    def create_variable (self, label, initial_values = None):
        # Always a list so we can know the len() of the variable value
        if type(initial_values) == list:
            initial_values = [self.try_int(entry) for entry in initial_values]
        elif type(initial_values) == str:
            initial_values = [self.try_int(initial_values)]
        elif type(initial_values) == int:
            initial_values = [initial_values]
        elif type(initial_values) == type(None):
            initial_values = [None]
        else:
            print("Unusable initial value {0} for variable {1}".format(label, initial_values))
            exit(1)
        new_variable = Variable(label = label, value = initial_values)
        return new_variable

    def lookup_variable (self, label, value = None, memory = None):
        """Locate variable if it exists. Search exhaustively to find duplicates."""
        memory, variable = (None, None)
        for memory_list in [self.shared, self.private, self.pointers, self.ports]:
            for entry in memory_list:
                if entry.label == label:
                    if memory is not None and variable is not None and label is not None:
                        print("Duplicate label found: {0}!".format(label))
                        exit(1)
                    memory, variable = memory_list, entry
                    # Now undo that if we have more things to match that fail.
                    if value is not None:
                        if entry.value != value:
                            memory, variable = (None, None)
                    if memory is not None:
                        if entry.memory != memory:
                            memory, variable = (None, None)
        return (memory, variable)

    def allocate_private (self, label, initial_values = None):
        """Allocate, or return existing private variable. """
        memory, variable = self.lookup_variable(label)
        if memory != self.private and variable is not None:
            print("The label {0} is already in use by a non-private variable!".format(label))
            exit(1)
        if variable is None:
            variable = self.create_variable(label, initial_values = initial_values)
            self.private.append(variable)
        return variable

    def allocate_shared (self, label, initial_values = None):
        """Allocate, or return existing shared variable."""
        memory, variable = self.lookup_variable(label, [initial_values], self.shared)
        if memory != self.shared and variable is not None:
            print("The label {0} is already in used by a non-shared variable!".format(label))
            exit(1)
        if variable is None:
            variable = self.create_variable(label, initial_values = initial_values)
            self.shared.append(variable)
        return variable

    def allocate_pointer (self, label, read_base = None, read_incr = None, write_base = None, write_incr = None):
        # We can't determine the init data value until we know which Data Memory it's read from.
        # This also affects the placement of the referred-to pointer/array.
        # The bases are labels until resolved to addresses
        read_incr   = int(read_incr, 0)
        write_incr  = int(write_incr, 0)
        # assign next consecutive slot (later improve to grant first freed slot)
        slot        = len(self.pointers)
        new_pointer = Pointer(label = label, read_base = read_base, read_incr = read_incr, write_base = write_base, write_incr = write_incr)
        self.pointers.append(new_pointer)
        return new_pointer

    def allocate_port (self, label, memory, number):
        number      = int(number, 0)
        new_port    = Port(label = label, number = number, memory = memory)
        self.ports.append(new_port)
        return new_port

    def next_variable_address (self, variables, memory):
        # No variable at address zero, ever. (Zero Register)
        # Add the length of the data of the max-addressed variable
        # so we return the next address just past its value(s)
        # Find in the same memory only, of course
        max_address     = 0
        max_data_length = 1

        # Find the higest set address in the given memory
        for variable in variables:
            address = variable.address
            if address is not None and variable.memory == memory:
                if address > max_address:
                    max_address     = address
                    max_data_length = len(variable.value)
        next_address =  max_address + max_data_length

        # Limit the address to the given range of the variables (shared, private, etc...)
        # We assume shared starts at zero
        if variables == self.shared and next_address not in self.configuration.memory_map.shared:
            print("Out of bounds address {0} for shared variable. Limit is {1}.".format(next_address, self.configuration.memory_map.shared[-1]))
            exit(1)

        if variables == self.private and next_address not in self.configuration.memory_map.private:
            # Catch the first private variable and put it at the start of the private area, the rest will follow.
            if next_address < self.configuration.memory_map.private[0]:
                next_address = self.configuration.memory_map.private[0]
            else:
                # Then it's greater...
                print("Out of bounds address {0} for private variable. Limit is {1}".format(next_address, self.configuration.memory_map.private[-1]))
                exit(1)

        return next_address

    def next_pointer_slot (self, pointers):
        # Pointer slots start at zero
        max_slot = -1
        for pointer in pointers:
            slot = pointer.slot
            if slot is not None:
                max_slot = max(slot, max_slot)
        return max_slot + 1

    def lookup_shared_value (self, value):
        entries = []
        for entry in self.shared:
            # Skip shared variables that have not been set a value
            # We don't collapse those into previously allocated values,
            # assuming they will get one later.
            # Find it in existing *unlabelled* shared variables.
            # meaning: other identical literals
            if entry.value == value and entry.value != [None] and entry.label is None:
                entries.append(entry)
        return entries

    def resolve_shared (self, value, memory):
        entries = self.lookup_shared_value(value)
        # Is there one in the memory we specified?
        entries = [entry for entry in entries if entry.memory == memory]
        # If not, create it!
        if entries == []:
            entry = self.allocate_shared(None, initial_values = value)
            entry.memory = memory
            entries.append(entry)
        if len(entries) > 1:
            print("Duplicate shared variables with value {0} in memory {1}!".format(value, memory))
            exit(1)
        # At this point, we're found or created our entry
        entry = entries[0]
        if entry.address is None:
            entry.address = self.next_variable_address(self.shared, memory)
#        if entry.memory != memory and entry.memory is not None:
#            print("Conflicting memory allocation for shared value {0}. Was {1}, now {2}".format(value, entry.memory, memory))
#            exit(1)
#        entry.memory = memory 
        return entry

    def resolve_named (self, name, memory):
        memory_list, entry = self.lookup_variable(name)

        if memory_list is None:
            print("Unknown label {0}".format(name))
            exit(1)

        if memory_list == self.shared:
            if entry.address is None:
                entry.address = self.next_variable_address(self.shared, memory)
            if entry.memory != memory and entry.memory is not None:
                print("Conflicting memory allocation for shared variable {0}. Was {1}, now {2}".format(name, entry.memory, memory))
                exit(1)
            entry.memory = memory 
            return entry.address

        if memory_list == self.private:
            if entry.address is None:
                entry.address = self.next_variable_address(self.private, memory)
            if entry.memory != memory and entry.memory is not None:
                print("Conflicting memory allocation for private variable {0}. Was {1}, now {2}".format(name, entry.memory, memory))
                exit(1)
            entry.memory = memory 
            return entry.address

        if memory_list == self.ports:
            if entry.address is None:
                entry.address = self.configuration.memory_map.io[entry.number]
            if entry.memory != memory:
                print("Conflicting memory allocation for I/O port {0}. Was {1}, now {2}".format(name, entry.memory, memory))
                exit(1)
            return entry.address
            
        if memory_list == self.pointers:
            if entry.slot is None:
                entry.slot = self.next_pointer_slot(self.pointers)
            if entry.address is None:
                entry.address = self.configuration.memory_map.indirect[entry.slot]
            if entry.memory != memory and entry.memory is not None:
                print("Conflicting memory allocation for pointer {0}. Was {1}, now {2}".format(name, entry.memory, memory))
                exit(1)
            entry.memory = memory 
            return entry.address
            
        
