"""
Searchlight:
The searchlight [Kriegeskorte 06] is a widely used approach for the study
of the fine-grained patterns of information in fMRI analysis.
Its principle is relatively simple: a small group of neighboring features
is extracted from the data, and the prediction function is instantiated
on these features only. The resulting prediction accuracy is thus associated
with all the features within the group, or only with the feature on the center.
This yields a map of local fine-grained information, that can be used for
assessing hypothesis on the local spatial layout of the neural
code under investigation.

Nikolaus Kriegeskorte, Rainer Goebel & Peter Bandettini.
Information-based functional brain mapping.
Proceedings of the National Academy of Sciences
of the United States of America,
vol. 103, no. 10, pages 3863-3868, March 2006
"""

#Authors : Vincent Michel (vm.michel@gmail.com)
#          Alexandre Gramfort (alexandre.gramfort@inria.fr)
#
#License: BSD 3 clause

import numpy as np

from joblib.parallel import Parallel, delayed

from sklearn.svm import LinearSVC
from sklearn.cross_validation import cross_val_score
from sklearn.base import BaseEstimator
from sklearn import neighbors


def search_light(X, y, estimator, A, score_func=None, cv=None, n_jobs=-1,
                 verbose=True):
    """
    Function for computing a search_light

    Parameters
    ----------
    X: array-like of shape at least 2D
        The data to fit.

    y: array-like
        The target variable to try to predict.

    estimator: estimator object implementing 'fit'
        The object to use to fit the data

    A : sparse matrix.
        adjacency matrix. Defines for each sample the neigbhoring samples
        following a given structure of the data.

    score_func: callable, optional
        callable taking as arguments the fitted estimator, the
        test data (X_test) and the test target (y_test) if y is
        not None.

    cv: cross-validation generator, optional
        A cross-validation generator. If None, a 3-fold cross
        validation is used or 3-fold stratified cross-validation
        when y is supplied.

    n_jobs: integer, optional
        The number of CPUs to use to do the computation. -1 means
        'all CPUs'.

    verbose: boolean, optional
        The verbosity level. Defaut is False

    Return
    ------
    scores: array-like of shape (number of rows in A)
        search_light scores
    """
    scores = np.zeros(len(A.rows), dtype=float)
    group_iter = GroupIterator(A.shape[0], n_jobs)
    scores = Parallel(n_jobs=n_jobs, verbose=verbose)(
              delayed(_group_iter_search_light)(list_i, A.rows[list_i],
              estimator, X, y, A.shape[0], score_func, cv, verbose)
              for list_i in group_iter)
    return np.concatenate(scores)


class GroupIterator(object):
    """Group iterator

    Provides group of features for search_light loop
    that may be used with Parallel.

    Parameters
    ===========
    n_features: int
        Total number of features
    n_jobs: integer, optional
        The number of CPUs to use to do the computation. -1 means
        'all CPUs'. Defaut is 1
    """

    def __init__(self, n_features, n_jobs=1):
        self.n_features = n_features
        if n_jobs == -1:
            import multiprocessing
            n_jobs = multiprocessing.cpu_count()
        self.n_jobs = n_jobs

    def __iter__(self):
        frac = np.int(self.n_features / self.n_jobs)
        for i in range(self.n_jobs):
            if i != (self.n_jobs - 1):
                list_i = range(i * frac, (i + 1) * frac)
            else:
                list_i = range(i * frac, self.n_features)
            yield list_i


def _group_iter_search_light(list_i, list_rows, estimator, X, y, total,
                            score_func, cv, verbose):
    """
    Function for grouped iterations of search_light

    Parameters
    -----------
    list_i: array of integers
        Indices of voxels to be processed by the thread.

    list_rows: array of array of integers
        Indices of adjacency rows corresponding to list_i voxels

    estimator: estimator object implementing 'fit'
        The object to use to fit the data

    X: array-like of shape at least 2D
        The data to fit.

    y: array-like
        The target variable to try to predict.

    total: integer
        Total number of voxels

    score_func: callable, optional
        callable taking as arguments the fitted estimator, the
        test data (X_test) and the test target (y_test) if y is
        not None.

    cv: cross-validation generator, optional
        A cross-validation generator. If None, a 3-fold cross
        validation is used or 3-fold stratified cross-validation
        when y is supplied.

    verbose: boolean, optional
        The verbosity level. Defaut is False

    Return
    ------
    par_scores: array of float
        precision of each voxel
    """
    par_scores = np.zeros(len(list_rows))
    for i, row in enumerate(list_rows):
        if list_i[i] not in row:
            row.append(list_i[i])
        par_scores[i] = np.mean(cross_val_score(estimator, X[:, row],
                y, score_func, cv, n_jobs=1))
        if verbose:
            print "Processing voxel #%d on %d. Precision is %2.2f" %\
                (list_i[i], total, par_scores[i])
    return par_scores


##############################################################################
### Class for search_light ###################################################
##############################################################################


class SearchLight(BaseEstimator):
    """
    SearchLight class.
    Class to perform a search_light using an arbitrary type of classifier.

    Parameters
    -----------
    mask : boolean matrix.
        data mask

    radius: float, optional
        radius of the searchlight sphere

    estimator: estimator object implementing 'fit'
        The object to use to fit the data

    n_jobs: integer, optional. Default is -1.
        The number of CPUs to use to do the computation. -1 means
        'all CPUs'.

    score_func: callable, optional
        callable taking as arguments the fitted estimator, the
        test data (X_test) and the test target (y_test) if y is
        not None.

    cv: cross-validation generator, optional
        A cross-validation generator. If None, a 3-fold cross
        validation is used or 3-fold stratified cross-validation
        when y is supplied.

    verbose: boolean, optional
        The verbosity level. Defaut is False
    """

    def __init__(self, mask, process_mask=None, radius=2.,
            estimator=LinearSVC(C=1), n_jobs=-1, score_func=None, cv=None,
            verbose=False):
        if process_mask is None:
            process_mask = mask
        clf = neighbors.NearestNeighbors(radius=radius)
        mask_indices = np.asarray(np.where(mask != 0)).T
        process_mask_indices = np.asarray(np.where(process_mask != 0)).T
        A = clf.fit(mask_indices).radius_neighbors_graph(process_mask_indices)
        self.A = A.tolil()
        self.mask = mask
        self.process_mask = process_mask
        self.estimator = estimator
        self.n_jobs = n_jobs
        self.score_func = score_func
        self.cv = cv
        self.verbose = verbose

    def fit(self, X, y):
        """
        Fit the search_light

        X: array-like of shape at least 2D
            The data to fit.

        y: array-like
            The target variable to try to predict.

        Attributes
        ----------
        scores: array-like of shape (number of rows in A)
            search_light scores
        """
        X_masked = X[:, self.mask]
        # scores is an array of CV scores with same cardinality as process_mask
        scores = search_light(X_masked, y, self.estimator, self.A,
            self.score_func, self.cv, self.n_jobs, self.verbose)
        scores_3D = np.zeros(self.process_mask.shape)
        scores_3D[self.process_mask] = scores
        self.scores = np.ma.array(scores_3D,
            mask=np.logical_not(self.process_mask))
        return self