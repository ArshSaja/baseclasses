"""
==============================================================================
BaseClasses: Solver History Class
==============================================================================

@Description : A general solver history class for storing values from a nonlinear solution.
"""

# ==============================================================================
# Standard Python modules
# ==============================================================================
from collections import OrderedDict
import copy
import os
import time
from typing import Optional, Type, Dict, Any, List, Iterable, Union
import pickle
import warnings


class HistoryVariable(object):
    """The HistoryVariable class is used to store the history of a single variable during the execution of a solver.

    NOTE: This class is intended only to be used within the SolverHistory class, and should not be used directly.
    """

    __slots__ = [
        "_name",
        "_type",
        "_valueFormat",
        "_headerFormat",
        "_data",
    ]

    def __init__(self, name: str, varType: Type, valueFormat: Optional[str] = None, headerFormat: Optional[str] = None):
        """Create a HistoryVariable object

        Parameters
        ----------
        name : str
            Name of the variable
        varType : Type
            Variable value type, i.e int, float, str etc
        valueFormat : Optional[str], optional
            Format string valid for printing variable values with the str.format() method (e.g "{:17.11e}" for a float
            or "{:03d}" for an int), only important for variables that are to be printed. By default None
        headerFormat : Optional[str], optional
            Format string valid for printing variable name with the str.format() method (e.g "{:^20}" to print the name
            centred in 20 columns), only important for variables that are to be printed. By default None
        """
        self._name: str = name
        self._type: Type = varType
        self._valueFormat: Optional[str] = valueFormat
        self._headerFormat: Optional[str] = headerFormat
        self._data: List = []

    def getName(self) -> str:
        """Return name of the variable"""
        return copy.deepcopy(self._name)

    def getType(self) -> Type:
        """Return type of the variable"""
        return self._type

    def reset(self) -> None:
        """Reset the variable history to its initial state."""
        self._data = []

    def write(self, value: Any) -> None:
        """Record data for a single iteration"""
        if value is None:
            self._data.append(None)
        else:
            # Store data, only if the supplied data can be converted to the correct type
            try:
                convertedValue = self._type(value)
                self._data.append(convertedValue)
            except ValueError as e:
                raise TypeError(
                    f"Value '{value}' provided for variable '{self._name}' could not be converted to the type declared for this variable: {self._type}"
                ) from e

    def writeFullHistory(self, values: Iterable) -> None:
        """Write the entire history of the variable in one go"""
        try:
            self._data = [None if v is None else self._type(v) for v in values]
        except ValueError as e:
            raise TypeError(
                f"A value provided for variable '{self._name}' could not be converted to the type declared for this variable: {self._type}"
            ) from e

    def getData(self) -> List:
        """Return the recorded data for this variable

        Returns
        -------
        List
            Recorded data for this variable, None values indicate iteration where no value was provided for this
            variable
        """
        return copy.deepcopy(self._data)

    def getValue(self, iteration: int) -> Any:
        """Return the value of the variable for a given iteration

        Parameters
        ----------
        iteration : int
            Iteration number to get value for

        Returns
        -------
        Any
            Value of the variable for the given iteration

        Raises
        ------
        IndexError
            Error is raised if the iteration number is out of range
        """
        try:
            return self._data[iteration]
        except IndexError as e:
            raise IndexError(f"Iteration {iteration} is out of range for variable {self._name}") from e

    def getFormattedHeaderString(self, string: Optional[str] = None) -> str:
        """Format a string in the header format for this variable

        Parameters
        ----------
        string : str, optional
            String to be formatted, by default uses self._name

        Returns
        -------
        str
            Formatted string

        Raises
        ------
        ValueError
            Error is raised if this method is called when no headerFormat has been defined
        """
        if self._headerFormat is None:
            raise ValueError(f"No header format specified for variable {self._name}")
        if string is None:
            string = self._name
        return self._headerFormat.format(string)

    def getFormattedValueString(self, val) -> str:
        """Format a string in the value format for this variable

        Parameters
        ----------
        val : Any
            Value to be formatted

        Returns
        -------
        str
            Formatted string

        Raises
        ------
        ValueError
            Error is raised if this method is called when no valueFormat has been defined
        """
        if self._valueFormat is None:
            raise ValueError(f"No print format specified for variable {self._name}")
        return self._valueFormat.format(val)


class SolverHistory(object):
    """The SolverHistory class can be used to store and print various useful values during the execution of a solver.

    NOTE: The implementation of this class contains no consideration of parallelism. If you are using a solverHistory
    object in your parallel solver, you will need to take care over which procs you make calls to the SolverHistory
    object on.
    """

    __slots__ = [
        "_variables",
        "_printVariables",
        "_metadata",
        "_iter",
        "_startTime",
        "_defaultFormat",
        "_includeIter",
        "_includeTime",
        "_DEFAULT_OTHER_FORMAT",
    ]

    def __init__(self, includeIter: bool = True, includeTime: bool = True) -> None:
        """Create a solver history instance

        Parameters
        ----------
        includeIter : bool, optional
            Whether to include the history's internal iteration variable in the history, by default True
        includeTime : bool, optional
            Whether to include the history's internal timing variable in the history, by default True
        """
        # Dictionaries for storing variable information and values
        self._variables: Dict[str, HistoryVariable] = OrderedDict()
        self._printVariables: Dict[str, bool] = {}
        self._metadata: Dict[str, Any] = {}

        # Initialise iteration counter and solve start time
        self._iter: int = 0
        self._startTime: float = -1.0

        # --- Define default print formatting for some common types ---
        self._defaultFormat: Dict[Type, str] = {}
        # float
        self._defaultFormat[float] = "{: 17.11e}"
        # complex
        self._defaultFormat[complex] = "{: 9.3e}"
        # int
        self._defaultFormat[int] = "{: 5d}"
        # str
        self._defaultFormat[str] = "{:^10}"
        # other
        self._DEFAULT_OTHER_FORMAT: str = "{}"

        # Add fields for the iteration number and time, unless the user excluded them
        self._includeIter = includeIter
        if self._includeIter:
            self.addVariable("Iter", varType=int, printVar=True)

        self._includeTime = includeTime
        if self._includeTime:
            self.addVariable("Time", varType=float, printVar=True, valueFormat="{:9.3e}")

    def reset(self, clearMetadata: bool = False) -> None:
        """Reset the history to its initial state.

        Parameters
        ----------
        clearMetadata : bool, optional
            Whether to clear the metadata too, by default False
        """

        # Reset iteration counter
        self._iter = 0

        # Reset solve start time
        self._startTime = -1.0

        # Clear recorded data
        for variable in self._variables.values():
            variable.reset()

        # Clear metadata if required
        if clearMetadata:
            self._metadata = {}

    def addMetadata(self, name: str, data: Any) -> None:
        """Add a piece of metadata to the history

        The metadata attribute is simply a dictionary that can be used to store arbitrary information related to the
        solution being recorded, e.g solver options

        Parameters
        ----------
        name : str
            Item name/key
        data : Any
            Item to store
        """
        self._metadata[name] = data

    def addVariable(
        self,
        name: str,
        varType: Type,
        printVar: bool = False,
        valueFormat: Optional[str] = None,
        overwrite: bool = False,
    ) -> None:
        """Define a new field to be stored in the history.

        Parameters
        ----------
        name : str
            Variable name
        varType : Type
            Variable type, i.e int, float, str etc
        printVar : bool, optional
            Whether to include the variable in the iteration printout, by default False
        valueFormat : str, optional
            Format string valid for use with the str.format() method (e.g "{:17.11e}" for a float or "{:03d}" for an
            int), only important for variables that are to be printed. By default a predefined format for the given
            `varType` is used
        overwrite : bool, optional
            Whether to overwrite any existing variables with the same name, by default False
        """

        if not overwrite and name in self._variables:
            warnings.warn(f"Variable '{name}' already defined, set `overwrite=True` to overwrite")
        else:
            if valueFormat is not None:
                pass
            elif varType in self._defaultFormat:
                valueFormat = self._defaultFormat[varType]
            else:
                valueFormat = self._DEFAULT_OTHER_FORMAT

            # Figure out column width, the maximum of the length of the name and the formatted value, also check
            # that the format string is valid by testing it on the default value for the provided varType
            try:
                testString = valueFormat.format(varType())
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f'Supplied format string "{valueFormat}" is invalid for variable type {varType}'
                ) from e

            dataLen = len(testString)
            nameLen = len(name)
            columnWidth = max(dataLen, nameLen)

            # --- Now figure out the format strings for the iteration printout header and values ---
            # The header is simply centred in the available width, which is actually columnWidth + 4
            headerFormat = f"{{:^{(columnWidth + 4)}s}}"

            self._variables[name] = HistoryVariable(name, varType, valueFormat, headerFormat)
            self._printVariables[name] = printVar

    def startTiming(self) -> None:
        """Record the start time of the solver

        This function only needs to be called explicitly if the start time of your solver is separate from the first
        time the `write` method is called.
        """
        self._startTime = time.time()

    def write(self, data: dict) -> None:
        """Record data for a single iteration

        Note that each call to this method is treated as a new iteration. All data to be recorded for a single solver
        iteration must therefore be recorded in a single call to this method.

        Parameters
        ----------
        data : dict
            Dictionary of values to record, with variable names as keys
        """

        # Store time
        if self._includeTime:
            if self._startTime < 0.0:
                self.startTiming()
                data["Time"] = 0.0
            else:
                data["Time"] = time.time() - self._startTime

        # Store iteration number
        if self._includeIter:
            data["Iter"] = self._iter

        for variable in self._variables.values():
            try:
                variable.write(data.pop(variable.getName()))
            # If no data was supplied for a given variable, store a None
            except KeyError:
                variable.write(None)

        # Any remaining entries in the data dictionary are variables that have not been defined using addVariable(), throw an error
        if len(data) > 0:
            raise ValueError(
                f"Unknown variables {data.keys()} supplied to Solution History recorder, recorded variables are {self.getVariables()}"
            )

        # Increment iteration counter
        self._iter += 1

    def writeFullVariableHistory(self, name: str, values: Iterable) -> None:
        """Write the entire history of a variable in one go

        This function should be used in the case where your solver already handles the recording of variables during a
        solution (e.g ADflow) but you want to use a SolverHistory object to facilitate writing it to a file

        Parameters
        ----------
        name : str
            Variable name
        values : Iterable
            Values to record, will be converted to a list
        """
        if name not in self._variables:
            raise ValueError(
                f"Unknown variables {name} supplied to Solution History recorder, recorded variables are {self.getVariables()}"
            )
        self._variables[name].writeFullHistory(values)

    def printHeader(self) -> None:
        """Print the header of the iteration printout

        The header will look something like this:

        .. code-block:: text

            +--------------------------------------------------------------------...------+
            |  Iter   |    Time     |  Random Int  |     Random Float     |      ...      |
            +--------------------------------------------------------------------...------+
        """

        # Each field will be `columnWidth` characters wide plus 2 spaces each side, plus the vertical bar between each
        # field
        headerString = "|"
        for variable in self._variablesToPrint:
            headerString += variable.getFormattedHeaderString()
            headerString += "|"
        headerWidth = len(headerString)

        headerBar = "+" + "-" * (headerWidth - 2) + "+"
        print(headerBar)
        print(headerString)
        print(headerBar)

    def printData(self, iters: Optional[Union[int, Iterable[int]]] = None) -> None:
        """Print a selection of lines from the history

        Each line will look something like this:

        .. code-block:: text

            |      0  |  1.000e-01  |      -84     |   2.87098307489e-01  |      ...      |


        Parameters
        ----------
        iters : int or Iterable of ints, optional
            Iteration numbers to print, by default only the last iteration will be printed
        """
        if iters is None:
            iters = [-1]
        elif isinstance(iters, int):
            iters = [iters]

        if max(iters) >= self._iter or min(iters) < -self._iter:
            if max(iters) >= self._iter:
                badIter = max(iters)
            else:
                badIter = min(iters)
            raise ValueError(
                f"Requested iteration {badIter} (zero-based) is not in the history, only {self._iter} iterations in history"
            )

        for i in iters:
            lineString = "|"
            for variable in self._variablesToPrint:
                data = variable.getValue(i)
                if data is None:
                    lineString += variable.getFormattedHeaderString("-")
                else:
                    valueString = variable.getFormattedValueString(data)
                    lineString += variable.getFormattedHeaderString(valueString)
                lineString += "|"
            print(lineString)

    def save(self, fileName: str) -> None:
        """Write the solution history to a pickle file

        Only the data dictionary is saved

        Parameters
        ----------
        fileName : str
            File path to save the solution history to, file extension not required, will be ignored if supplied
        """
        base = os.path.splitext(fileName)[0]
        fileName = base + ".pkl"

        dataToSave = {"data": self.getData(), "metadata": self.getMetadata()}
        with open(fileName, "wb") as file:
            pickle.dump(dataToSave, file, protocol=pickle.HIGHEST_PROTOCOL)

    def getData(self) -> Dict[str, List]:
        """Get the recorded data

        Returns
        -------
        dict
            Dictionary of recorded data
        """
        data = {}
        for varName, variable in self._variables.items():
            data[varName] = copy.deepcopy(variable.getData())
        return data

    def getMetadata(self) -> Dict[str, Any]:
        """Get the recorded metadata

        Returns
        -------
        dict
            Dictionary of recorded metadata
        """
        return copy.deepcopy(self._metadata)

    def getVariables(self) -> List[str]:
        """Get the recorded variables

        Returns
        -------
        dict
            Dictionary of recorded variables
        """
        return list(self._variables.keys())

    def getIter(self) -> int:
        """Get the current number of iterations recorded

        Returns
        -------
        int
            Number of iterations recorded
        """
        return copy.copy(self._iter)

    @property
    def _variablesToPrint(self) -> List[HistoryVariable]:
        """Get the variables to print

        Returns
        -------
        list
            List of variables to print
        """
        return [self._variables[varName] for varName in self._printVariables if self._printVariables[varName]]
