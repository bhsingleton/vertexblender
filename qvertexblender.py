import os
import fnmatch
import webbrowser

from PySide2 import QtCore, QtWidgets, QtGui
from functools import partial
from six import string_types

from dcc import fnscene, fncallbacks, fnnode, fnskin
from dcc.userinterface import qproxywindow, iconutils

from .dialogs import qeditinfluencesdialog, qeditweightsdialog

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def validate(func):
    """
    Method wrapper used to validate the internal skin weights variable before calling the passed function.
    :param func: Python function to be called after validation.
    :return: See passed function for details.
    """

    # Define wrapper function
    #
    def wrapper(*args, **kwargs):

        # Check if skin deformer is valid
        #
        window = args[0]

        if window.skin.isValid():

            return func(*args, **kwargs)

        else:

            return

    return wrapper


class QInfluenceFilterModel(QtCore.QSortFilterProxyModel):
    """
    Overload of QSortFilterProxyModel used to filter out influence names.
    """

    __pending__ = False

    def __init__(self, *args, **kwargs):
        """
        Overloaded method called after a new instance has been created.
        """

        # Call parent method
        #
        super(QInfluenceFilterModel, self).__init__(*args, **kwargs)

        # Declare class variables
        #
        self._siblingModel = None
        self._visible = []
        self._selectedRows = []
        self._overrides = []
        self._autoSelect = True
        self._activeInfluences = []
        self._inactiveInfluences = []

    def filterAcceptsRow(self, row, parent):
        """
        Overloaded method used to dynamically hide/show rows based on the return value.

        :type row: int
        :type parent: QtCore.QModelIndex
        :rtype: bool
        """

        # Check if row contains null data
        #
        index = self.sourceModel().index(row, 0, parent)

        if self.isItemNull(index):

            log.debug('%s contains null data.' % row)
            self._inactiveInfluences.append(row)

            return False

        # Check if row should be visible
        #
        acceptsRow = False

        if row in self._visible or row in self._selectedRows:

            # Append item to active influences
            #
            self._activeInfluences.append(row)
            acceptsRow = True

        elif row in self._overrides:

            self._activeInfluences.append(row)
            self._overrides.remove(row)

            acceptsRow = True

        else:

            log.debug('%s is marked as hidden.' % row)
            self._inactiveInfluences.append(row)

        return acceptsRow

    def invalidateFilter(self):
        """
        Overloaded method used to clear influence lists before filtering any rows.

        :rtype: None
        """

        # Reset private lists
        #
        self._activeInfluences = []
        self._inactiveInfluences = []

        # Call inherited method
        #
        super(QInfluenceFilterModel, self).invalidateFilter()

    def sourceWidget(self):
        """
        Property method used to return the associated widget with this filter model.
        There is a bug in Maya 2017 related to the overloaded "parent" method.
        Super must be invoked to circumvent this issue.

        :rtype: QtWidgets.QAbstractItemView
        """

        return super(QtCore.QAbstractItemModel, self.sourceModel()).parent()

    def siblingModel(self):
        """
        Method used to retrieve the sibling model used for matching selections.

        :rtype: InfluenceFilterProxyModel
        """

        return self._siblingModel

    def setSiblingModel(self, model):
        """
        Method used to update the sibling model that is responsible for syncing selections.

        :type model: InfluenceFilterProxyModel
        :rtype: None
        """

        # Check value type
        #
        if not isinstance(model, QtCore.QSortFilterProxyModel):

            raise TypeError('setSiblingModel() expects QSortFilterProxyModel (%s given)!' % type(model).__name__)

        # Assign private property
        #
        self._siblingModel = model

    def autoSelect(self):
        """
        Method used to check if auto select is enabled.

        :rtype: bool
        """

        return self._autoSelect

    def setAutoSelect(self, autoSelect):
        """
        Setter method with keyword arguments to control invalidation.

        :type autoSelect: bool
        :rtype: None
        """

        # Check value type
        #
        if not isinstance(autoSelect, bool):

            raise TypeError('setAutoSelect() expects a bool (%s given)!' % type(autoSelect).__name__)

        # Assign private property
        #
        self._autoSelect = autoSelect

        # Sync selections
        #
        if self._autoSelect:

            self.matchSelection()

    def visible(self):
        """
        Retrieves a list of indices that should be visible when filtering.

        :rtype: list[int]
        """

        return self._visible

    @property
    def numVisible(self):
        """
        Getter method used to determine the number of visible items.

        :rtype: int
        """

        return len(self._visible)

    def setVisible(self, *args, **kwargs):
        """
        Setter method used to set the protected list value.

        :type args: tuple[int]
        :type kwargs: dict
        :rtype: None
        """

        # Check argument types
        #
        if not all([isinstance(x, int) for x in args]):

            raise TypeError('setVisible() expects a sequence of integers!')

        # Reset private variables
        #
        self._visible = args
        self.invalidateFilter()

    def selectedRows(self):
        """
        Retrieves a list of rows that should be selected.

        :rtype: list[int]
        """

        return self._selectedRows

    def setSelectedRows(self, selectedRows):
        """
        Updates the list of rows that should be selected.
        This method emits no signals and is purely for optimization purposes.

        :rtype: list[int]
        """

        self._selectedRows = list(selectedRows)

    def overrides(self):
        """
        Retrieves a list of overrides that can bypass filtering.
        These items are gradually removed by the "filterAcceptsRow" method.

        :rtype: list[int]
        """

        return self._overrides

    def setOverrides(self, *args):
        """
        Setter method used to retrieve the current overrides for this model.

        :type args: tuple[int]
        :rtype: None
        """

        # Check argument types
        #
        if not all([isinstance(x, int) for x in args]):

            raise TypeError('setOverrides() expects a sequence of integers!')

        # Reset private variables
        #
        self._overrides = list(args)
        self.invalidateFilter()

    @property
    def activeInfluences(self):
        """
        Getter method used to access the active influence list.

        :rtype: list[int]
        """

        return self._activeInfluences

    @property
    def numActiveInfluences(self):
        """
        Getter method used to determine the number of active influences.

        :rtype: int
        """

        return len(self._activeInfluences)

    @property
    def inactiveInfluences(self):
        """
        Getter method used to retrieve the inactive influences.

        :rtype: list[int]
        """

        return self._inactiveInfluences

    @property
    def numInactiveInfluences(self):
        """
        Getter method used to retrieve the number of inactive influences.

        :rtype: int
        """

        return len(self._inactiveInfluences)

    @classmethod
    def beginSelectionUpdate(cls):
        """
        Changes the filter state to prevent cyclical errors.

        :rtype: None
        """

        cls.__pending__ = True

    @classmethod
    def endSelectionUpdate(cls):
        """
        Changes the filter state to prevent cyclical errors.

        :rtype: None
        """

        cls.__pending__ = False

    def matchSelection(self):
        """
        Attempts to match the selections between the two sibling models.

        :rtype: None
        """

        # Check if there's already a pending operation
        #
        if self.isPending():

            return

        # Sync selections by blocking other tasks
        #
        self.beginSelectionUpdate()
        self.siblingModel().selectInfluences(self._selectedRows)
        self.endSelectionUpdate()

    @classmethod
    def isPending(cls):
        """
        Class method used to determine if this model is currently matching selections.

        :rtype: bool
        """

        return cls.__pending__

    def isItemNull(self, index):
        """
        Checks if the supplied row contains any data.

        :type index: QtCore.QModelIndex
        :rtype: bool
        """

        # Check if index is valid
        #
        if index.isValid():

            return not self.sourceModel().itemFromIndex(index).text()

        else:

            return True

    def isRowHidden(self, row):
        """
        Checks if the supplied row is hidden.

        :type row: int
        :rtype: bool
        """

        return row in self._inactiveInfluences

    def isRowSelected(self, row, column=0):
        """
        Method used to check if the supplied row index is selected.

        :type row: int
        :type column: int
        :rtype: bool
        """

        # Check value type
        #
        if not isinstance(row, int):

            raise TypeError('isRowSelected() expects a int (%s given)!' % row)

        # Get selection model
        #
        sourceModel = self.sourceModel()
        selectionModel = super(QtCore.QAbstractItemModel, sourceModel).parent().selectionModel()

        # Define model index
        #
        index = sourceModel.index(row, column)
        index = self.mapFromSource(index)

        return selectionModel.isSelected(index)

    def getRowsByText(self, texts, column=0):
        """
        Gets the row associated with the supplied text.

        :type texts: list[str]
        :type column: int
        :rtype: list[int]
        """

        # Check value types
        #
        if isinstance(texts, (list, tuple, set)):

            # Get associate model and iterate through items
            #
            sourceModel = self.sourceModel()
            rows = []

            for text in texts:

                items = sourceModel.findItems(text, column=column)
                rows = rows + [x.row() for x in items]

            log.debug('Got %s row indices from %s names.' % (rows, texts))
            return rows

        elif isinstance(texts, string_types):

            return self.getRowsByText([texts], column=0)

        else:

            return []

    def selectInfluences(self, rows):
        """
        Selects the supplied row indices.

        :type rows: list[int]
        :rtype: None
        """

        # Check value type
        #
        if not all([isinstance(x, int) for x in rows]):

            raise TypeError('selectInfluences() expects a sequence of integers!')

        # Get source and selection model
        #
        sourceModel = self.sourceModel()
        selectionModel = super(QtCore.QAbstractItemModel, sourceModel).parent().selectionModel()

        # Collect all valid row indices
        #
        numRows = len(rows)
        numColumns = sourceModel.columnCount()

        # Un-hide any rows that may be hidden
        #
        hidden = [x for x in rows if self.isRowHidden(x)]
        numHidden = len(hidden)

        if numHidden > 0:

            self.setOverrides(*hidden)

        # Check if any rows have been supplied
        #
        log.debug('Attempting to select %s...' % rows)

        if numRows > 0:

            # Iterate through rows and build item selection
            #
            itemSelection = QtCore.QItemSelection()

            for row in rows:

                # Remap indices using source model
                #
                topLeft = sourceModel.index(row, 0)
                bottomRight = sourceModel.index(row, numColumns - 1)

                selection = QtCore.QItemSelection(topLeft, bottomRight)
                itemSelection.merge(selection, QtCore.QItemSelectionModel.Select)

            # Map selection to filter model
            #
            itemSelection = self.mapSelectionFromSource(itemSelection)
            selectionModel.select(itemSelection, QtCore.QItemSelectionModel.ClearAndSelect)

            # Scroll to last row
            #
            index = sourceModel.index(rows[0], 0)
            index = self.mapFromSource(index)

            self.sourceWidget().scrollTo(index)

        else:

            # Check if there are any active influences
            #
            if self.numActiveInfluences > 0:

                # Get first influence
                #
                activeInfluence = self._activeInfluences[0]

                # Define model index
                #
                topLeft = sourceModel.index(activeInfluence, 0)
                bottomRight = sourceModel.index(activeInfluence, numColumns - 1)

                itemSelection = QtCore.QItemSelection(topLeft, bottomRight)
                itemSelection = self.mapSelectionFromSource(itemSelection)

                # Select index and scroll to top
                #
                selectionModel.select(itemSelection, QtCore.QItemSelectionModel.ClearAndSelect)
                self.sourceWidget().scrollToTop()

            else:

                log.debug('Unable to perform selection change request.')

    def getSelectedRows(self):
        """
        Gets the selected row indices from the source widget.

        :rtype: list[int]
        """

        # Get the selection model
        #
        selectionModel = self.sourceWidget().selectionModel()

        # Map selection model to the filter model
        #
        selection = selectionModel.selection()
        selection = self.mapSelectionToSource(selection)

        # Create unique list of rows
        #
        indices = selection.indexes()
        selectedRows = set([x.row() for x in indices])

        return list(selectedRows)

    def getSelectedItems(self, column=0):
        """
        Gets the selected items based on the specified column.
        By default this is set to 0 since we're more concerned with influence names.

        :param column: Forces the operation to query a different column.
        :type column: int
        :rtype: list[str]
        """

        # Get corresponding text value from row indices
        #
        sourceModel = self.sourceModel()
        rows = self.getSelectedRows()

        return [sourceModel.item(x, column).text() for x in rows]

    def filterRowsByPattern(self, pattern, column=0):
        """
        Method used to generate a filtered list of row items based on a supplied pattern.

        :type pattern: str
        :type column: int
        :rtype: list(int)
        """

        # Check value type
        #
        if not isinstance(pattern, string_types):

            raise ValueError('Unable to filter rows using %s type!' % type(pattern).__name__)

        # Get text values from source model
        #
        sourceModel = self.sourceModel()
        rows = range(sourceModel.rowCount())

        # Compose list using match pattern
        #
        items = [sourceModel.item(row, column).text() for row in rows]
        filtered = [row for row, item in zip(rows, items) if fnmatch.fnmatch(item, pattern)]

        return filtered

    def onSelectionChanged(self, selected, deselected):
        """
        Slot method called whenever the active selection changes.

        :type selected: QItemSelection
        :type deselected: QItemSelection
        :rtype: None
        """

        # Inspect selected indices
        #
        rows = self.getSelectedRows()
        numRows = len(rows)

        if numRows == 0:

            log.debug('Current source model contains no rows.')
            return

        # Store selection change
        #
        self.setSelectedRows(rows)
        self.invalidateFilter()

        # Check if precision mode is enabled
        #
        if self._autoSelect:

            self.matchSelection()

        else:

            log.debug('Selection update is not required.')

        # Force connection change
        #
        QVertexBlender.getInstance().requestInfluenceChange()


class QVertexBlender(qproxywindow.QProxyWindow):
    """
    Overload of QProxyWindow used to manipulate vertex weights.
    """

    def __init__(self, *args, **kwargs):
        """
        Private method called after a new instance has been created.

        :keyword parent: QtWidgets.QWidget
        :keyword flags: QtCore.Qt.WindowFlags
        :rtype: None
        """

        # Call parent method
        #
        super(QVertexBlender, self).__init__(*args, **kwargs)

        # Declare private variables
        #
        self._skin = fnskin.FnSkin()
        self._softSelection = {}
        self._vertices = {}
        self._vertexWeights = {}
        self._precision = False
        self._selectShell = False
        self._slabOption = 0
        self._search = ''
        self._mirrorAxis = 0
        self._clipboard = None
        self._selectionChangedId = None
        self._undoId = None
        self._redoId = None
        self._settings = QtCore.QSettings('Ben Singleton', 'Vertex Blender')

        # Declare public variables
        #
        self.clipboard = None
        self.previousInfluences = []
        self.previousWeights = []

    def __build__(self):
        """
        Private method used to build the user interface.

        :rtype: None
        """

        # Define window properties
        #
        self.setWindowTitle('|| Vertex Blender')
        self.setMinimumSize(QtCore.QSize(385, 555))

        # Create central widget
        #
        self.setCentralWidget(QtWidgets.QWidget())
        self.centralWidget().setLayout(QtWidgets.QVBoxLayout())

        # Create menu bar
        #
        self.setMenuBar(QtWidgets.QMenuBar())

        # Create file menu
        #
        self.fileMenu = QtWidgets.QMenu('&File', parent=self.menuBar())
        self.fileMenu.setSeparatorsCollapsible(False)
        self.fileMenu.setTearOffEnabled(True)
        self.fileMenu.setWindowTitle('File')

        self.saveWeightsAction = QtWidgets.QAction('&Save Weights ', self.fileMenu)
        self.saveWeightsAction.triggered.connect(self.saveWeights)

        self.loadWeightsAction = QtWidgets.QAction('&Load Weights ', self.fileMenu)
        self.loadWeightsAction.triggered.connect(self.loadWeights)

        self.menuBar().addMenu(self.fileMenu)
        self.fileMenu.addAction(self.saveWeightsAction)
        self.fileMenu.addAction(self.loadWeightsAction)

        # Create edit menu
        #
        self.editMenu = QtWidgets.QMenu('&Edit', parent=self.menuBar())
        self.editMenu.setSeparatorsCollapsible(False)
        self.editMenu.setTearOffEnabled(True)
        self.editMenu.setWindowTitle('Edit')

        self.copyWeightsAction = QtWidgets.QAction('&Copy Weights', self.editMenu)
        self.copyWeightsAction.triggered.connect(self.copyWeights)

        self.pasteWeightsAction = QtWidgets.QAction('&Paste Weights', self.editMenu)
        self.pasteWeightsAction.triggered.connect(self.pasteWeights)

        self.pasteAverageWeightsAction = QtWidgets.QAction('&Paste Average Weights', self.editMenu)
        self.pasteAverageWeightsAction.triggered.connect(self.pasteAverageWeights)

        self.blendVerticesAction = QtWidgets.QAction('&Blend Vertices', self.editMenu)
        self.blendVerticesAction.triggered.connect(self.blendVertices)

        self.blendBetweenVerticesAction = QtWidgets.QAction('&Blend Between Vertices', self.editMenu)
        self.blendBetweenVerticesAction.triggered.connect(self.blendBetweenVertices)

        self.blendBetweenTwoVerticesAction = QtWidgets.QAction('&Blend Between Two Vertices', self.editMenu)
        self.blendBetweenTwoVerticesAction.triggered.connect(self.blendBetweenTwoVertices)

        self.blendByDistanceAction = QtWidgets.QAction('&Blend By Distance', self.editMenu)
        self.blendByDistanceAction.setCheckable(True)

        self.seatSkinAction = QtWidgets.QAction('&Reset Intermediate Object', self.editMenu)
        self.seatSkinAction.triggered.connect(self.resetIntermediateObject)

        self.resetInfluencesAction = QtWidgets.QAction('&Reset Bind-Pre Matrices', self.editMenu)
        self.resetInfluencesAction.triggered.connect(self.resetBindPreMatrices)

        self.menuBar().addMenu(self.editMenu)

        self.editMenu.addSection('Copy/Paste Weights')
        self.editMenu.addAction(self.copyWeightsAction)
        self.editMenu.addAction(self.pasteWeightsAction)
        self.editMenu.addAction(self.pasteAverageWeightsAction)

        self.editMenu.addSection('Vertex Weight Blending')
        self.editMenu.addAction(self.blendVerticesAction)
        self.editMenu.addAction(self.blendBetweenVerticesAction)
        self.editMenu.addAction(self.blendBetweenTwoVerticesAction)
        self.editMenu.addAction(self.blendByDistanceAction)

        self.editMenu.addSection('Modify Skin Cluster')
        self.editMenu.addAction(self.seatSkinAction)
        self.editMenu.addAction(self.resetInfluencesAction)

        # Create settings menu
        #
        self.settingsMenu = QtWidgets.QMenu('&Settings', parent=self.menuBar())
        self.settingsMenu.setSeparatorsCollapsible(False)
        self.settingsMenu.setTearOffEnabled(True)
        self.settingsMenu.setWindowTitle('Settings')

        self.mirrorAxisSeparator = QtWidgets.QAction('Mirror-Axis', self.editMenu)
        self.mirrorAxisSeparator.setSeparator(True)

        self.mirrorAxisGroup = QtWidgets.QActionGroup(self.editMenu)
        self.mirrorAxisGroup.setExclusive(True)
        self.mirrorAxisGroup.triggered.connect(self.mirrorAxisChanged)

        self.xAction = QtWidgets.QAction('&X', self.editMenu)
        self.xAction.setActionGroup(self.mirrorAxisGroup)
        self.xAction.setCheckable(True)
        self.xAction.setChecked(QtCore.Qt.CheckState.Checked)

        self.yAction = QtWidgets.QAction('&Y', self.editMenu)
        self.yAction.setActionGroup(self.mirrorAxisGroup)
        self.yAction.setCheckable(True)

        self.zAction = QtWidgets.QAction('&Z', self.editMenu)
        self.zAction.setActionGroup(self.mirrorAxisGroup)
        self.zAction.setCheckable(True)

        self.setMirrorToleranceAction = QtWidgets.QAction('Set Mirror Threshold', self.settingsMenu)
        self.setMirrorToleranceAction.triggered.connect(self.changeMirrorTolerance)

        self.colorRampAction = QtWidgets.QAction('Use Color Ramp', self.settingsMenu)
        self.colorRampAction.setCheckable(True)
        self.colorRampAction.setChecked(True)

        self.menuBar().addMenu(self.settingsMenu)
        self.settingsMenu.addAction(self.mirrorAxisSeparator)
        self.settingsMenu.addAction(self.xAction)
        self.settingsMenu.addAction(self.yAction)
        self.settingsMenu.addAction(self.zAction)
        self.settingsMenu.addSection('Mirror Tolerance')
        self.settingsMenu.addAction(self.setMirrorToleranceAction)
        self.settingsMenu.addSection('Vertex Weight Display')
        self.settingsMenu.addAction(self.colorRampAction)

        # Create debug menu
        #
        self.debugMenu = QtWidgets.QMenu('&Debug', self.menuBar())
        self.debugMenu.setSeparatorsCollapsible(False)
        self.debugMenu.setTearOffEnabled(True)
        self.debugMenu.setWindowTitle('Debug')

        self.resetInfluencesAction = QtWidgets.QAction('&Reset Active Selection', self.editMenu)
        self.resetInfluencesAction.setCheckable(True)

        self.menuBar().addMenu(self.debugMenu)
        self.debugMenu.addAction(self.resetInfluencesAction)

        # Create help menu
        #
        self.helpMenu = QtWidgets.QMenu('&Help', parent=self.menuBar())
        self.helpMenu.setSeparatorsCollapsible(False)
        self.helpMenu.setTearOffEnabled(True)
        self.helpMenu.setWindowTitle('Help')

        self.helpAction = QtWidgets.QAction('&Using Vertex Blender', self.helpMenu)
        self.helpAction.triggered.connect(self.requestHelp)

        self.menuBar().addMenu(self.helpMenu)
        self.helpMenu.addAction(self.helpAction)

        # Create toggle widgets
        #
        self.envelopeLayout = QtWidgets.QVBoxLayout()

        self.envelopeGroupBox = QtWidgets.QGroupBox('')
        self.envelopeGroupBox.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.envelopeGroupBox.setLayout(self.envelopeLayout)

        self.envelopeButton = QtWidgets.QPushButton('Edit Envelope')
        self.envelopeButton.setCheckable(True)
        self.envelopeButton.toggled.connect(self.envelopeChanged)

        self.envelopeLayout.addWidget(self.envelopeButton)
        self.centralWidget().layout().addWidget(self.envelopeGroupBox)

        # Set style sheet for toggle button
        #
        self.envelopeButton.setStyleSheet(
            'QPushButton:hover:checked {\n' +
            '   background-color: crimson;\n' +
            '}\n' +
            'QPushButton:checked {\n' +
            '   background-color: firebrick;\n' +
            '   border: none;\n' +
            '}'
        )

        # Create main splitter
        #
        self.centralSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.centralWidget().layout().addWidget(self.centralSplitter)

        # Add influences table widget
        #
        self.influenceLayout = QtWidgets.QVBoxLayout()

        self.influenceGrpBox = QtWidgets.QGroupBox('Influences:')
        self.influenceGrpBox.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.influenceGrpBox.setMinimumWidth(130)
        self.influenceGrpBox.setLayout(self.influenceLayout)

        self.influenceTable = QtWidgets.QTableView()
        self.influenceTable.setShowGrid(True)
        self.influenceTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.influenceTable.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.influenceTable.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.influenceTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.influenceTable.horizontalHeader().setStretchLastSection(True)
        self.influenceTable.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        self.influenceModel = QtGui.QStandardItemModel(0, 1, parent=self.influenceTable)
        self.influenceModel.setHorizontalHeaderLabels(['Influences'])

        self.influenceFilterModel = QInfluenceFilterModel()
        self.influenceFilterModel.setSourceModel(self.influenceModel)

        self.influenceTable.setModel(self.influenceFilterModel)
        self.influenceTable.selectionModel().selectionChanged.connect(self.influenceFilterModel.onSelectionChanged)

        self.searchBox = QtWidgets.QLineEdit('')
        self.searchBox.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.searchBox.setFixedHeight(23)
        self.searchBox.textChanged.connect(self.searchChanged)
        self.searchBox.returnPressed.connect(self.searchPressed)

        self.searchBtn = QtWidgets.QPushButton(iconutils.getIconByName('search'), '')
        self.searchBtn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.searchBtn.setFixedSize(QtCore.QSize(23, 23))
        self.searchBtn.clicked.connect(self.searchPressed)

        self.searchLayout = QtWidgets.QHBoxLayout()
        self.searchLayout.addWidget(self.searchBox)
        self.searchLayout.addWidget(self.searchBtn)

        self.manageLayout = QtWidgets.QHBoxLayout()

        self.addInfluencesBtn = QtWidgets.QPushButton('Add')
        self.addInfluencesBtn.clicked.connect(self.addInfluences)

        self.removeInfluenceBtn = QtWidgets.QPushButton('Remove')
        self.removeInfluenceBtn.clicked.connect(self.removeInfluences)

        self.manageLayout.addWidget(self.addInfluencesBtn)
        self.manageLayout.addWidget(self.removeInfluenceBtn)

        self.influenceLayout.addLayout(self.searchLayout)
        self.influenceLayout.addWidget(self.influenceTable)
        self.influenceLayout.addLayout(self.manageLayout)

        self.centralSplitter.addWidget(self.influenceGrpBox)

        # Create splitter layout for weight table
        #
        self.weightSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.weightSplitter.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.weightSplitter.setMinimumWidth(230)

        self.centralSplitter.addWidget(self.weightSplitter)

        # Create weight table
        #
        self.weightLayout = QtWidgets.QVBoxLayout()

        self.weightGrpBox = QtWidgets.QGroupBox('Weights:')
        self.weightGrpBox.setLayout(self.weightLayout)

        self.weightTable = QtWidgets.QTableView()
        self.weightTable.setShowGrid(True)
        self.weightTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.weightTable.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.weightTable.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.weightTable.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.weightTable.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.weightTable.doubleClicked.connect(self.onDoubleClick)
        self.weightTable.customContextMenuRequested.connect(self.requestCustomContextMenu)

        self.weightModel = QtGui.QStandardItemModel(0, 2, parent=self.weightTable)
        self.weightModel.setHorizontalHeaderLabels(['Joint', 'Weight'])

        self.weightFilterModel = QInfluenceFilterModel()
        self.weightFilterModel.setSourceModel(self.weightModel)

        self.weightTable.setModel(self.weightFilterModel)
        self.weightTable.selectionModel().selectionChanged.connect(self.weightFilterModel.onSelectionChanged)

        self.weightTable.setColumnWidth(1, 64)
        self.weightTable.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)
        self.weightTable.horizontalHeader().setStretchLastSection(False)
        self.weightTable.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)

        # Define sibling relationship between tables
        #
        self.influenceFilterModel.setSiblingModel(self.weightFilterModel)
        self.weightFilterModel.setSiblingModel(self.influenceFilterModel)

        # Create popup menu widget
        #
        self.popupMenu = QtWidgets.QMenu(self)

        self.selectVerticesAction = self.popupMenu.addAction('&Select Affected Vertices')
        self.selectVerticesAction.triggered.connect(self.selectAffectedVertices)

        # Create optional mode widgets
        #
        self.modeLayout = QtWidgets.QHBoxLayout()

        self.precisionCheckBox = QtWidgets.QCheckBox('Precision Mode')
        self.precisionCheckBox.toggled.connect(self.precisionChanged)

        self.selectShellCheckBox = QtWidgets.QCheckBox('Select Shell')
        self.selectShellCheckBox.toggled.connect(self.selectShellChanged)

        self.modeLayout.addWidget(self.precisionCheckBox)
        self.modeLayout.addWidget(self.selectShellCheckBox)

        self.weightLayout.addWidget(self.weightTable)
        self.weightLayout.addLayout(self.modeLayout)

        self.weightSplitter.addWidget(self.weightGrpBox)

        # Create options widgets
        #
        self.optionsLayout = QtWidgets.QVBoxLayout()

        self.optionsGrpBox = QtWidgets.QGroupBox('Options:')
        self.optionsGrpBox.setLayout(self.optionsLayout)

        self.mirrorLayout = QtWidgets.QHBoxLayout()

        self.mirrorButton = QtWidgets.QPushButton('Mirror')
        #self.mirrorButton.clicked.connect(partial(self.mirrorWeights, False))

        self.pullButton = QtWidgets.QPushButton('Pull')
        #self.pullButton.clicked.connect(partial(self.mirrorWeights, True))

        self.mirrorLayout.addWidget(self.mirrorButton)
        self.mirrorLayout.addWidget(self.pullButton)

        self.optionsLayout.addLayout(self.mirrorLayout)

        self.weightSplitter.addWidget(self.optionsGrpBox)

        # Create slab paste widgets
        #
        self.slabButton = QtWidgets.QPushButton('Slab')
        #self.slabButton.clicked.connect(self.slabPasteWeights)

        self.slabOptions = QtWidgets.QPushButton()
        self.slabOptions.setFixedWidth(18)
        self.slabOptions.setLayoutDirection(QtCore.Qt.RightToLeft)

        self.slabLayout = QtWidgets.QHBoxLayout()
        self.slabLayout.setSpacing(2)
        self.slabLayout.addWidget(self.slabButton)
        self.slabLayout.addWidget(self.slabOptions)

        self.slabMenu = QtWidgets.QMenu(self.slabOptions)

        self.slabGroup = QtWidgets.QActionGroup(self.slabButton)
        self.slabGroup.setExclusive(True)
        #self.slabGroup.triggered.connect(self.slabOptionChanged)

        self.closestPointAction = self.slabMenu.addAction('&Closest Point')
        self.closestPointAction.setCheckable(True)
        self.closestPointAction.setChecked(QtCore.Qt.CheckState.Checked)

        self.nearestNeighbourAction = self.slabMenu.addAction('&Nearest Neighbour')
        self.nearestNeighbourAction.setCheckable(True)

        self.alongNormalAction = self.slabMenu.addAction('&Along Normal')
        self.alongNormalAction.setCheckable(True)

        self.slabGroup.addAction(self.closestPointAction)
        self.slabGroup.addAction(self.nearestNeighbourAction)
        self.slabGroup.addAction(self.alongNormalAction)

        self.slabOptions.setMenu(self.slabMenu)

        self.mirrorLayout.addLayout(self.slabLayout)

        # Create set weight preset widgets
        #
        self.presetLayout = QtWidgets.QHBoxLayout()

        self.presetBtn1 = QtWidgets.QPushButton('0', self.optionsGrpBox)
        self.presetBtn1.clicked.connect(partial(self.applyPreset, 0.0))
        self.presetBtn2 = QtWidgets.QPushButton('.1', self.optionsGrpBox)
        self.presetBtn2.clicked.connect(partial(self.applyPreset, 0.1))
        self.presetBtn3 = QtWidgets.QPushButton('.25', self.optionsGrpBox)
        self.presetBtn3.clicked.connect(partial(self.applyPreset, 0.25))
        self.presetBtn4 = QtWidgets.QPushButton('.5', self.optionsGrpBox)
        self.presetBtn4.clicked.connect(partial(self.applyPreset, 0.5))
        self.presetBtn5 = QtWidgets.QPushButton('.75', self.optionsGrpBox)
        self.presetBtn5.clicked.connect(partial(self.applyPreset, 0.75))
        self.presetBtn6 = QtWidgets.QPushButton('.9', self.optionsGrpBox)
        self.presetBtn6.clicked.connect(partial(self.applyPreset, 0.9))
        self.presetBtn7 = QtWidgets.QPushButton('1', self.optionsGrpBox)
        self.presetBtn7.clicked.connect(partial(self.applyPreset, 1.0))

        self.presetLayout.addWidget(self.presetBtn1)
        self.presetLayout.addWidget(self.presetBtn2)
        self.presetLayout.addWidget(self.presetBtn3)
        self.presetLayout.addWidget(self.presetBtn4)
        self.presetLayout.addWidget(self.presetBtn5)
        self.presetLayout.addWidget(self.presetBtn6)
        self.presetLayout.addWidget(self.presetBtn7)

        self.optionsLayout.addLayout(self.presetLayout)

        # Create set weight widgets
        #
        self.setterLayout = QtWidgets.QHBoxLayout()

        self.setterLabel = QtWidgets.QLabel(self.optionsGrpBox)
        self.setterLabel.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.setterLabel.setFixedSize(QtCore.QSize(72, 23))
        self.setterLabel.setText('Set Weight:')
        self.setterLabel.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.setterSpinBox = QtWidgets.QDoubleSpinBox(self.optionsGrpBox)
        self.setterSpinBox.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.setterSpinBox.setFixedHeight(23)
        self.setterSpinBox.setMinimum(0.0)
        self.setterSpinBox.setMaximum(1.0)
        self.setterSpinBox.setValue(0.05)
        self.setterSpinBox.setSingleStep(0.01)
        self.setterSpinBox.setAlignment(QtCore.Qt.AlignHCenter)

        self.setterBtn = QtWidgets.QPushButton('Apply', self.optionsGrpBox)
        self.setterBtn.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        self.setterBtn.setFixedHeight(23)
        self.setterBtn.clicked.connect(partial(self.setWeights))

        self.setterLayout.addWidget(self.setterLabel)
        self.setterLayout.addWidget(self.setterSpinBox)
        self.setterLayout.addWidget(self.setterBtn)

        self.optionsLayout.addLayout(self.setterLayout)

        # Create increment weight widgets
        #
        self.incrementLayout = QtWidgets.QHBoxLayout()

        self.incrementLbl = QtWidgets.QLabel(self.optionsGrpBox)
        self.incrementLbl.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.incrementLbl.setFixedSize(QtCore.QSize(72, 23))
        self.incrementLbl.setText('Increment By:')
        self.incrementLbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.incrementSpinBox = QtWidgets.QDoubleSpinBox(self.optionsGrpBox)
        self.incrementSpinBox.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.incrementSpinBox.setFixedHeight(23)
        self.incrementSpinBox.setMinimum(0.0)
        self.incrementSpinBox.setMaximum(1.0)
        self.incrementSpinBox.setValue(0.05)
        self.incrementSpinBox.setSingleStep(0.01)
        self.incrementSpinBox.setAlignment(QtCore.Qt.AlignHCenter)

        self.incrementBtn1 = QtWidgets.QPushButton('+', self.optionsGrpBox)
        self.incrementBtn1.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.incrementBtn1.setFixedSize(QtCore.QSize(23, 23))
        self.incrementBtn1.clicked.connect(partial(self.incrementWeights, False))

        self.incrementBtn2 = QtWidgets.QPushButton('-', self.optionsGrpBox)
        self.incrementBtn2.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.incrementBtn2.setFixedSize(QtCore.QSize(23, 23))
        self.incrementBtn2.clicked.connect(partial(self.incrementWeights, True))

        self.incrementLayout.addWidget(self.incrementLbl)
        self.incrementLayout.addWidget(self.incrementSpinBox)
        self.incrementLayout.addWidget(self.incrementBtn1)
        self.incrementLayout.addWidget(self.incrementBtn2)

        self.optionsLayout.addLayout(self.incrementLayout)

        # Create scale weights widgets
        #
        self.scaleLayout = QtWidgets.QHBoxLayout()

        self.scaleLabel = QtWidgets.QLabel(self.optionsGrpBox)
        self.scaleLabel.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.scaleLabel.setFixedSize(QtCore.QSize(72, 23))
        self.scaleLabel.setText('Scale Weight:')
        self.scaleLabel.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.scaleSpinBox = QtWidgets.QDoubleSpinBox(self.optionsGrpBox)
        self.scaleSpinBox.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.scaleSpinBox.setFixedHeight(23)
        self.scaleSpinBox.setMinimum(0.0)
        self.scaleSpinBox.setMaximum(1.0)
        self.scaleSpinBox.setValue(0.1)
        self.scaleSpinBox.setSingleStep(0.01)
        self.scaleSpinBox.setAlignment(QtCore.Qt.AlignHCenter)

        self.scaleButton1 = QtWidgets.QPushButton('+', self.optionsGrpBox)
        self.scaleButton1.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.scaleButton1.setFixedSize(QtCore.QSize(23, 23))
        self.scaleButton1.clicked.connect(partial(self.scaleWeights, False))

        self.scaleButton2 = QtWidgets.QPushButton('-', self.optionsGrpBox)
        self.scaleButton2.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.scaleButton2.setFixedSize(QtCore.QSize(23, 23))
        self.scaleButton2.clicked.connect(partial(self.scaleWeights, True))

        self.scaleLayout.addWidget(self.scaleLabel)
        self.scaleLayout.addWidget(self.scaleSpinBox)
        self.scaleLayout.addWidget(self.scaleButton1)
        self.scaleLayout.addWidget(self.scaleButton2)

        self.optionsLayout.addLayout(self.scaleLayout)

    def showEvent(self, event):
        """
        Event method called after the window has been shown.

        :type event: QtGui.QShowEvent
        :rtype: None
        """

        # Modify window settings
        #
        keys = self._settings.allKeys()
        numKeys = len(keys)

        if numKeys > 0:

            self.resize(self._settings.value('editor/size'))
            self.move(self._settings.value('editor/pos'))

        # Call parent method
        #
        super(QVertexBlender, self).showEvent(event)

    def closeEvent(self, event):
        """
        Event method called after the window has been closed.

        :type event: QtGui.QCloseEvent
        :rtype: None
        """

        # Exit envelope mode
        #
        self.envelopeButton.setChecked(False)

        # Store window settings
        #
        self._settings.setValue('editor/size', self.size())
        self._settings.setValue('editor/pos', self.pos())

        log.info('Saving settings to: %s' % self._settings.fileName())

        # Call parent method
        #
        return super(QVertexBlender, self).closeEvent(event)

    @property
    def skin(self):
        """
        Getter method used to retrieve the selected skin cluster object.

        :rtype: fnskin.FnSkin
        """

        return self._skin

    def envelopeChanged(self, checked):
        """
        Slot method called whenever the user clicks the edit envelope button.

        :type checked: bool
        :rtype: None
        """

        # Reset standard item models
        #
        self.influenceModel.setRowCount(0)
        self.weightModel.setRowCount(0)

        # Check if envelope is checked
        #
        sender = self.sender()
        fnCallbacks = fncallbacks.FnCallbacks()

        if checked:

            # Evaluate active selection
            # If nothing is selected then uncheck button
            #
            selection = fnskin.FnSkin.getActiveSelection()
            selectionCount = len(selection)

            if selectionCount == 0:

                sender.setChecked(False)
                return

            # Try and set object
            # If selected node is invalid then uncheck button
            #
            success = self.skin.trySetObject(selection[0])

            if not success:

                sender.setChecked(False)
                return

            # Add callbacks
            #
            self._selectionChangedId = fnCallbacks.addComponentSelectionChangedCallback(self.invalidate)
            self._undoId = fnCallbacks.addUndoCallback(self.invalidateColors)
            self._redoId = fnCallbacks.addRedoCallback(self.invalidateColors)

            # Invalidate window
            #
            self.invalidateInfluences()
            self.invalidateWeights()

        else:

            # Check if function set still has an object attached
            # If so then we need to reset it and remove the previous callbacks
            #
            if self.skin.isValid():

                # Remove callbacks
                #
                self._selectionChangedId = fnCallbacks.removeCallback(self._selectionChangedId)
                self._undoId = fnCallbacks.removeCallback(self._undoId)
                self._redoId = fnCallbacks.removeCallback(self._redoId)

                # Reset object
                #
                self.skin.resetObject()

    @property
    def precision(self):
        """
        Method used to check if precision mode is enabled.

        :rtype: bool
        """

        return self._precision

    def precisionChanged(self, precision):
        """
        Slot method called whenever the user changes the precision check box.
        This method will update the behaviour of the table widgets.

        :type precision: bool
        :rtype: None
        """

        # Assign private property
        #
        self._precision = precision

        # Toggle auto select behaviour
        #
        if self._precision:

            # Change selection mode to extended
            #
            self.weightTable.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

            # Disable auto select
            #
            self.influenceFilterModel.setAutoSelect(False)
            self.weightFilterModel.setAutoSelect(False)

        else:

            # Change selection model to single
            #
            self.weightTable.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

            # Enable auto select
            #
            self.influenceFilterModel.setAutoSelect(True)
            self.weightFilterModel.setAutoSelect(True)

    @property
    def selectShell(self):
        """
        Getter method that returns a flag that indicates if shells should be selected.

        :rtype: bool
        """

        return self._selectShell

    def selectShellChanged(self, selectShell):
        """
        Event for capturing any changes made to the select shell property.

        :type selectShell: bool
        :rtype: None
        """

        self._selectShell = selectShell

    @property
    def mirrorTolerance(self):
        """
        Getter method that returns the mirror tolerance.

        :rtype: float
        """

        return self._settings.value('editor/mirrorTolerance')

    @mirrorTolerance.setter
    def mirrorTolerance(self, mirrorTolerance):
        """
        Setter method that updates the mirror tolerance.

        :type mirrorTolerance: float
        :rtype: None
        """

        self._settings.setValue('editor/mirrorTolerance', mirrorTolerance)

    def changeMirrorTolerance(self):
        """
        Method used to update the internal mirroring threshold.
        :rtype: None
        """

        # Define input dialog
        #
        threshold, ok = QtWidgets.QInputDialog.getDouble(
            self,
            'Set Mirror Threshold',
            'Enter radius for closest point consideration:',
            value=self.mirrorThreshold(),
            min=1e-3,
            decimals=3
        )

        # Check dialog result before setting value
        #
        if ok:

            self.mirrorTolerance = threshold

        else:

            log.info('Operation aborted...')

    @property
    def search(self):
        """
        Getter method that returns the search string.

        :rtype: str
        """

        return self._search

    def searchChanged(self, search):
        """
        Updates the user-defined search string.

        :type search: str
        :rtype: None
        """

        self._search = '*{search}*'.format(search=search)

    def searchPressed(self, checked=False):
        """
        Forces the influence model to filter the visible influences.

        :type checked: bool
        :rtype: None
        """

        visible = self.influenceFilterModel.filterRowsByPattern(self.search)
        self.influenceFilterModel.setVisible(*visible)

    def activeInfluence(self):
        """
        Property method for getting the active influence.
        :rtype: int
        """

        # Check active selection
        #
        selectedRows = self.influenceFilterModel.selectedRows()
        numSelected = len(selectedRows)

        if numSelected > 0:

            return selectedRows[0]

        else:

            raise TypeError('Unable to get active influence from current selection!')

    def sourceInfluences(self):
        """
        Gets all of the source influences to redistribute from using the selection model.

        :rtype: list[int]
        """

        # Get selected rows
        #
        selectedRows = self.weightFilterModel.selectedRows()
        numSelected = len(selectedRows)

        if numSelected == 0:

            raise TypeError('sourceInfluences() expects a valid selection!')

        # Check if tool is in lazy mode
        #
        influenceIds = []

        if self.precision:

            # Remove target influence if in source
            #
            influenceIds = selectedRows
            activeInfluence = self.activeInfluence()

            if activeInfluence in influenceIds:

                influenceIds.remove(activeInfluence)

        else:

            influenceIds = [x for x in self.weightFilterModel.activeInfluences if x not in selectedRows]

        # Return influence ids
        #
        log.debug('Source Influences: %s' % influenceIds)
        return influenceIds

    @validate
    def invalidate(self, *args, **kwargs):
        """
        Invalidates the data currently displayed to user.

        :rtype: None
        """

        self.invalidateWeights()
        self.invalidateColors()

    @validate
    def invalidateInfluences(self):
        """
        Invalidation method used to reset the influence list.

        :rtype: None
        """

        # Retrieve influence objects
        #
        influences = self.skin.influences()

        # Reset header labels
        #
        rowCount = influences.lastIndex() + 1
        labels = map(str, range(rowCount))

        self.influenceModel.setRowCount(rowCount)
        self.influenceModel.setVerticalHeaderLabels(labels)

        self.weightModel.setRowCount(rowCount)
        self.weightModel.setVerticalHeaderLabels(labels)

        # Assign influence items
        #
        fnInfluence = fnnode.FnNode()
        influenceIds = []

        for influenceId in range(rowCount):

            # Check if influence is valid
            #
            influence = influences[influenceId]

            success = fnInfluence.trySetObject(influence)
            influenceName = ''

            if success:

                influenceName = fnInfluence.name()
                influenceIds.append(influenceId)

            else:

                log.debug('No influence object found at ID: %s.' % influenceId)

            # Create influence table item
            #
            influenceItem = self.createStandardItem(influenceName)
            self.influenceModel.setItem(influenceId, influenceItem)

            # Create weights table items
            #
            nameItem = self.createStandardItem(influenceName)
            weightItem = self.createStandardItem('0.0')

            self.weightModel.setItem(influenceId, 0, nameItem)
            self.weightModel.setItem(influenceId, 1, weightItem)

        # Invalidate influence table
        #
        self.influenceFilterModel.setVisible(*influenceIds)
        self.influenceFilterModel.selectInfluences([0])

    @validate
    def invalidateWeights(self, *args, **kwargs):
        """
        Invalidation method used to reset the selection list.
        :rtype: None
        """

        # Get active selection
        #
        self._softSelection = self.skin.softSelection()

        selection = list(self._softSelection.keys())
        selectionCount = len(selection)

        # Store selected weights
        #
        self._vertices = self.skin.weights(*selection)

        if selectionCount == 0:

            self._vertexWeights = {}

        elif selectionCount == 1:

            self._vertexWeights = self._vertices[selection[0]]

        if selectionCount > 1:

            self._vertexWeights = self.skin.averageWeights(*list(self._vertices.values()), maintainMaxInfluences=False)

        # Check if there any values
        #
        numWeights = len(self._vertexWeights)

        if numWeights > 0:

            # Iterate through rows
            #
            numRows = self.weightModel.rowCount()

            for i in range(numRows):

                index = self.weightModel.index(i, 1)
                item = self.weightModel.itemFromIndex(index)

                weight = self._vertexWeights.get(i, 0.0)
                item.setText('%s' % round(weight, 3))

            # Invalidate filter model
            #
            influenceIds = self._vertexWeights.keys()
            self.weightFilterModel.setVisible(*influenceIds)

        else:

            log.debug('No vertex weights supplied to invalidate filter model.')

    @validate
    def invalidateColors(self, *args, **kwargs):
        """
        Invalidation method used to re-transfer paint weights onto color set.

        :rtype: None
        """

        pass

    @validate
    def requestInfluenceChange(self):
        """
        External method used to change the active influence on the skin cluster node.
        A custom MPxCommand will need to be loaded for this method to work!

        :rtype: None
        """

        self.skin.selectInfluence(self.activeInfluence())

    @validate
    def saveWeights(self):
        """
        Saves the skin weights from the active selection.

        :rtype: None
        """

        # Get default directory
        #
        fnScene = fnscene.FnScene()
        shapeName = fnnode.FnNode(self.skin.shape()).name()
        defaultFilePath = os.path.join(fnScene.currentDirectory(), '{name}.json'.format(name=shapeName))

        filePath, selectedFilter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            'Save Skin Weights',
            defaultFilePath,
            'All JSON Files (*.json)'
        )

        # Check if a file was specified
        #
        if len(filePath) > 0:

            log.info('Saving skin weights to: %s' % filePath)
            self.skin.saveWeights(filePath)

        else:

            log.info('Operation aborted...')

    @validate
    def loadWeights(self):
        """
        Loads skin weights onto the active selection.

        :rtype: None
        """

        # Get default directory
        #
        fnScene = fnscene.FnScene()
        defaultDirectory = fnScene.currentDirectory()

        # Prompt user for save path
        #
        filePath, selectedFilter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            'Save Skin Weights',
            defaultDirectory,
            'All JSON Files (*.json)'
        )

        if filePath:

            self.skin.saveWeights(filePath)
            log.info('Saving skin weights to: %s' % filePath)

        else:

            log.info('Operation aborted...')

    @validate
    def resetIntermediateObject(self):
        """
        Bakes the current pose into the skin cluster.

        :rtype: bool
        """

        # Prompt user
        #
        reply = QtWidgets.QMessageBox.question(
            self,
            'Seat Skin',
            'Are you sure you want to reset the intermediate object?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:

            pass

    @validate
    def resetBindPreMatrices(self):
        """
        Resets the bind-pre matrices on the skin cluster.

        :rtype: bool
        """

        # Prompt user
        #
        reply = QtWidgets.QMessageBox.question(
            self,
            'Reset Influences',
            'Are you sure you want to reset the bind-pre matrices?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:

            pass

    def requestCustomContextMenu(self, point):
        """
        Trigger function used to display a context menu under certain conditions.
        :type point: QtCore.QPoint
        :rtype: None
        """

        numRows = self.weightModel.rowCount()
        hasSelection = self.weightTable.selectionModel().hasSelection()

        if numRows > 1 and hasSelection:

            return self.popupMenu.exec_(self.weightTable.mapToGlobal(point))

    def onDoubleClick(self, index):
        """
        Selects the text value from the opposite table.

        :type index: QtCore.QModelIndex
        :rtype: None
        """

        # Map index to filter model
        #
        index = self.weightFilterModel.mapToSource(index)

        # Get row from remapped index
        #
        row = index.row()
        column = index.column()

        text = self.weightModel.item(row, column).text()
        log.debug('User has double clicked %s influence.' % text)

        # Select row with text
        #
        self.influenceFilterModel.selectInfluences([row])

    @property
    def mirrorAxis(self):
        """
        Getter method used to retrieve the current mirror axis.

        :rtype: int
        """

        return self._mirrorAxis

    def mirrorAxisChanged(self, action):
        """
        Slot method called whenever the user changes the mirror axis.

        :type action: QtWidgets.QAction
        :rtype: None
        """

        self._mirrorAxis = self.sender().actions().index(action)

    @property
    def slabOption(self):
        """
        Getter method used to retrieve the current slab option.

        :rtype: int
        """

        return self._slabOption

    def slabOptionChanged(self, action):
        """
        Slot method called whenever the user changes the slab option.

        :type action: QtWidgets.QAction
        :rtype: None
        """

        self._slabOption = self.sender().actions().index(action)

    @validate
    def selectAffectedVertices(self):
        """
        Removes all selected influences from the selected vertices.
        :rtype: None
        """

        # Get selected rows
        #
        selectedRows = self.weightFilterModel.getSelectedRows()

        # Update active selection
        #
        selection = self.skin.getVerticesByInfluenceId(selectedRows)
        self.skin.setSelection(selection)

    @validate
    def addInfluences(self):
        """
        Add influences to the selected skin cluster.

        :rtype: None
        """

        qeditinfluencesdialog.addInfluences(self.skin.object())
        self.invalidateInfluences()

    @validate
    def removeInfluences(self):
        """
        Removes influences from the selected skin cluster.

        :rtype: None
        """

        qeditinfluencesdialog.removeInfluences(self.skin.object())
        self.invalidateInfluences()

    @validate
    def copyWeights(self):
        """
        Copies the selected vertex weights to the clipboard.

        :rtype: None
        """

        self.skin.copyWeights()

    @validate
    def pasteWeights(self):
        """
        Pastes weights from the clipboard to the active selection.

        :rtype: None
        """

        self.skin.pasteWeights()
        self.invalidateWeights()

    @validate
    def pasteAverageWeights(self):
        """
        Pastes averaged weights from the clipboard to the active selection.

        :rtype: None
        """

        self.skin.pasteAveragedWeights()
        self.invalidateWeights()

    @validate
    def blendVertices(self):
        """
        Blends the selected vertices.

        :rtype: None
        """

        self.skin.blendVertices()
        self.invalidateWeights()

    @validate
    def blendBetweenVertices(self):
        """
        Blends the skin weights between a continuous line of vertices.

        :rtype: None
        """

        self.skin.blendBetweenVertices(blendByDistance=self.blendByDistanceAction.isChecked())
        self.invalidateWeights()

    @validate
    def blendBetweenTwoVertices(self):
        """
        Blends the skin weights between two vertices using the shortest path.

        :rtype: None
        """

        self.skin.blendBetweenTwoVertices(blendByDistance=self.blendByDistanceAction.isChecked())
        self.invalidateWeights()

    @validate
    def applyPreset(self, amount):
        """
        Sets the skin weights to the pre-defined value.

        :type amount: float
        :rtype: None
        """

        # Get setter arguments
        #
        activeInfluence = self.activeInfluence()
        sourceInfluences = self.sourceInfluences()

        # Iterate through selection
        #
        updates = {}

        for (vertexIndex, falloff) in self._softSelection.items():

            updates[vertexIndex] = self.skin.setWeights(
                self._vertices[vertexIndex],
                activeInfluence,
                sourceInfluences,
                amount,
                falloff=falloff
            )

        # Assign updates to skin
        #
        self.skin.applyWeights(updates)
        self.invalidateWeights()

    @validate
    def setWeights(self):
        """
        Sets the selected vertex weights to the specified amount.

        :rtype: None
        """

        # Get setter arguments
        #
        activeInfluence = self.activeInfluence()
        sourceInfluences = self.sourceInfluences()
        amount = self.setterSpinBox.value()

        # Iterate through selection
        #
        updates = {}

        for (vertexIndex, falloff) in self._softSelection.items():

            updates[vertexIndex] = self.skin.setWeights(
                self._vertices[vertexIndex],
                activeInfluence,
                sourceInfluences,
                amount,
                falloff=falloff
            )

        # Assign updates to skin
        #
        self.skin.applyWeights(updates)
        self.invalidateWeights()

    @validate
    def incrementWeights(self, pull):
        """
        Increments the selected vertex weights by the specified amount.

        :type pull: bool
        :rtype: None
        """

        # Get increment arguments
        #
        activeInfluence = self.activeInfluence()
        sourceInfluences = self.sourceInfluences()
        amount = self.incrementSpinBox.value()

        if pull:

            amount *= -1.0

        # Iterate through selection
        #
        updates = {}

        for (vertexIndex, falloff) in self._softSelection.items():

            updates[vertexIndex] = self.skin.incrementWeights(
                self._vertices[vertexIndex],
                activeInfluence,
                sourceInfluences,
                amount,
                falloff=falloff
            )

        # Assign updates to skin
        #
        self.skin.applyWeights(updates)
        self.invalidateWeights()

    @validate
    def scaleWeights(self, pull):
        """
        Scales the selected vertex weights by the specified amount.

        :type pull: bool
        :rtype: None
        """

        # Get scale arguments
        #
        activeInfluence = self.activeInfluence()
        sourceInfluences = self.sourceInfluences()
        percent = self.scaleSpinBox.value()

        if pull:

            percent *= -1.0

        # Iterate through selection
        #
        updates = {}

        for (vertexIndex, falloff) in self._softSelection.items():

            updates[vertexIndex] = self.skin.scaleWeights(
                self._vertices[vertexIndex],
                activeInfluence,
                sourceInfluences,
                percent,
                falloff=falloff
            )

        # Assign updates to skin
        #
        self.skin.applyWeights(updates)
        self.invalidateWeights()

    @validate
    def mirrorWeights(self, pull):
        """
        Mirrors the selected vertex weights across the mesh.

        :type pull: bool
        :rtype: bool
        """

        # Get debug option before mirroring
        #
        resetActiveSelection = self.resetInfluencesAction.isChecked()
        selection = self.skin.selection()

        self.skin.mirrorVertices(
            selection,
            pull=pull,
            resetActiveSelection=resetActiveSelection
        )

        self.invalidateWeights()

    @validate
    def slabPasteWeights(self):
        """
        Trigger method used to copy the selected vertex influences to the nearest neighbour.
        See "getSlabMethod" for details.

        :rtype: bool
        """

        # Get slab option before pasting
        #
        self.skin.slabPasteWeights(slabOption=self.slabOption)
        self.invalidateWeights()

    def requestHelp(self):
        """
        Opens a web browser to the documentation page on github.

        :rtype: None
        """

        webbrowser.open('https://github.com/bhsingleton/vertexblender')
