"""
This module defines tensors with abstract index notation.

The abstract index notation has been first formalized by Penrose.

Tensor indices are formal objects, with a tensor type; there is no
notion of index range, it is only possible to assign the dimension,
used to trace the Kronecker delta; the dimension can be a Symbol.

The Einstein summation convention is used.
The covariant indices are indicated with a minus sign in front of the index.

For instance the tensor ``t = p(a)*A(b,c)*q(-c)`` has the index ``c``
contracted.

A tensor expression ``t`` can be called; called with its
indices in sorted order it is equal to itself:
in the above example ``t(a, b) == t``;
one can call ``t`` with different indices; ``t(c, d) == p(c)*A(d,a)*q(-a)``.

The contracted indices are dummy indices, internally they have no name,
the indices being represented by a graph-like structure.

Tensors are put in canonical form using ``canon_bp``, which uses
the Butler-Portugal algorithm for canonicalization using the monoterm
symmetries of the tensors.

If there is a (anti)symmetric metric, the indices can be raised and
lowered when the tensor is put in canonical form.
"""

from __future__ import print_function, division

from collections import defaultdict
from sympy.core import Basic, sympify, Add, S
from sympy.core.symbol import Symbol, symbols
from sympy.core.compatibility import string_types
from sympy.combinatorics.tensor_can import get_symmetric_group_sgs, bsgs_direct_product, canonicalize, riemann_bsgs
from sympy.core.containers import Tuple
from sympy import Matrix, Rational
from sympy.external import import_module
from sympy.utilities.decorator import doctest_depends_on


class TIDS(object):
    """
    Tensor internal data structure. This contains internal data about
    components of a tensor expression, its free and dummy indices.

    To create a `TIDS` object via the standard constructor, the required
    arguments are

    ``components``  `TensorHead` objects representing the components
                    of the tensor expression.

    ``free``        Free indices in their internal representation.

    ``dum``         Dummy indices in their internal representation.

    Examples
    ========

    >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, TIDS, tensorhead
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> m0, m1, m2, m3 = tensor_indices('m0,m1,m2,m3', Lorentz)
    >>> T = tensorhead('T', [Lorentz]*4, [[1]*4])
    >>> TIDS([T], [(m0, 0, 0), (m3, 3, 0)], [(1, 2, 0, 0)])
    TIDS([T(Lorentz,Lorentz,Lorentz,Lorentz)], [(m0, 0, 0), (m3, 3, 0)], [(1, 2, 0, 0)])

    Details
    =======

    In short, this has created the components, free and dummy indices for
    the internal representation of a tensor T(m0, m1, -m1, m3).

    Free indices are represented as a list of triplets. The elements of
    each triplet identify a single free index and are

    1. TensorIndex object
    2. position inside the component
    3. component number

    Dummy indices are represented as a list of 4-plets. Each 4-plet stands
    for couple for contracted indices, their original TensorIndex is not
    stored as it is no longer required. The four elements of the 4-plet
    are

    1. position inside the component of the first index.
    2. position inside the component of the second index.
    3. component number of the first index.
    4. component number of the second index.

    """

    def __init__(self, components, free, dum):
        self.components = components
        self.free = free
        self.dum = dum
        self._ext_rank = len(self.free) + 2*len(self.dum)

    def get_components_with_free_indices(self):
        """
        Get a list of components with their associated indices.

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, TIDS, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> m0, m1, m2, m3 = tensor_indices('m0,m1,m2,m3', Lorentz)
        >>> T = tensorhead('T', [Lorentz]*4, [[1]*4])
        >>> A = tensorhead('A', [Lorentz], [[1]])
        >>> t = TIDS.from_components_and_indices([T], [m0, m1, -m1, m3])
        >>> t.get_components_with_free_indices()
        [(T(Lorentz,Lorentz,Lorentz,Lorentz), [(m0, 0, 0), (m3, 3, 0)])]
        >>> t2 = (A(m0)*A(-m0))._tids
        >>> t2.get_components_with_free_indices()
        [(A(Lorentz), []), (A(Lorentz), [])]
        >>> t3 = (A(m0)*A(-m1)*A(-m0)*A(m1))._tids
        >>> t3.get_components_with_free_indices()
        [(A(Lorentz), []), (A(Lorentz), []), (A(Lorentz), []), (A(Lorentz), [])]
        >>> t4 = (A(m0)*A(m1)*A(-m0))._tids
        >>> t4.get_components_with_free_indices()
        [(A(Lorentz), []), (A(Lorentz), [(m1, 0, 1)]), (A(Lorentz), [])]
        >>> t5 = (A(m0)*A(m1)*A(m2))._tids
        >>> t5.get_components_with_free_indices()
        [(A(Lorentz), [(m0, 0, 0)]), (A(Lorentz), [(m1, 0, 1)]), (A(Lorentz), [(m2, 0, 2)])]
        """
        components = self.components
        ret_comp = []

        free_counter = 0
#        dum_counter1 = 0
#        dum_counter2 = 0
        if len(self.free) == 0:
            return [(comp, []) for comp in components]

        for i, comp in enumerate(components):
            c_free = []
            while free_counter < len(self.free):
                if not self.free[free_counter][2] == i:
                    break

                c_free.append(self.free[free_counter])
                free_counter += 1

                if free_counter >= len(self.free):
                    break
            ret_comp.append((comp, c_free))

        return ret_comp

    @staticmethod
    def from_components_and_indices(components, indices):
        """
        Create a new `TIDS` object from `components` and `indices`

        ``components``  `TensorHead` objects representing the components
                        of the tensor expression.

        ``indices``     `TensorIndex` objects, the indices. Contractions are
                        detected upon construction.

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, TIDS, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> m0, m1, m2, m3 = tensor_indices('m0,m1,m2,m3', Lorentz)
        >>> T = tensorhead('T', [Lorentz]*4, [[1]*4])
        >>> TIDS.from_components_and_indices([T], [m0, m1, -m1, m3])
        TIDS([T(Lorentz,Lorentz,Lorentz,Lorentz)], [(m0, 0, 0), (m3, 3, 0)], [(1, 2, 0, 0)])

        In case of many components the same indices have slightly different
        indexes:

        >>> A = tensorhead('A', [Lorentz], [[1]])
        >>> TIDS.from_components_and_indices([A]*4, [m0, m1, -m1, m3])
        TIDS([A(Lorentz), A(Lorentz), A(Lorentz), A(Lorentz)], [(m0, 0, 0), (m3, 0, 3)], [(0, 0, 1, 2)])
        """
        tids = None
        cur_pos = 0
        for i in components:
            tids_sing = TIDS([i], *TIDS.free_dum_from_indices(*indices[cur_pos:cur_pos+i.rank]))
            if tids is None:
                tids = tids_sing
            else:
                tids *= tids_sing
            cur_pos += i.rank

        if tids is None:
            tids = TIDS([], [], [])

        tids.free.sort(key=lambda x: x[0].name)
        tids.dum.sort()

        return tids

    def to_indices(self):
        """
        Get a list of indices, creating new tensor indices to complete dummy indices.
        """
        component_indices = []
        for i in self.components:
            component_indices.append([None]*i.rank)

        for i in self.free:
            component_indices[i[2]][i[1]] = i[0]

        for i, dummy_pos in enumerate(self.dum):
            tensor_index_type = self.components[dummy_pos[2]].args[1].args[0][0]
            dummy_index = TensorIndex('dummy_index_{0}'.format(i), tensor_index_type)
            component_indices[dummy_pos[2]][dummy_pos[0]] = dummy_index
            component_indices[dummy_pos[3]][dummy_pos[1]] = -dummy_index

        indices = []
        for i in component_indices:
            indices.extend(i)

        return indices

    @staticmethod
    def free_dum_from_indices(*indices):
        """
        Convert ``indices`` into ``free``, ``dum`` for single component tensor

        ``free``     list of tuples ``(index, pos, 0)``,
                     where ``pos`` is the position of index in
                     the list of indices formed by the component tensors

        ``dum``      list of tuples ``(pos_contr, pos_cov, 0, 0)``

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, TIDS
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> m0, m1, m2, m3 = tensor_indices('m0,m1,m2,m3', Lorentz)
        >>> TIDS.free_dum_from_indices(m0, m1, -m1, m3)
        ([(m0, 0, 0), (m3, 3, 0)], [(1, 2, 0, 0)])
        """
        n = len(indices)
        if n == 1:
            return [(indices[0], 0, 0)], []

        # find the positions of the free indices and of the dummy indices
        free = [True]*len(indices)
        index_dict = {}
        dum = []
        for i, index in enumerate(indices):
            name = index._name
            typ = index._tensortype
            contr = index._is_up
            if (name, typ) in index_dict:
                # found a pair of dummy indices
                is_contr, pos = index_dict[(name, typ)]
                # check consistency and update free
                if is_contr:
                    if contr:
                        raise ValueError('two equal contravariant indices in slots %d and %d' %(pos, i))
                    else:
                        free[pos] = False
                        free[i] = False
                else:
                    if contr:
                        free[pos] = False
                        free[i] = False
                    else:
                        raise ValueError('two equal covariant indices in slots %d and %d' %(pos, i))
                if contr:
                    dum.append((i, pos, 0, 0))
                else:
                    dum.append((pos, i, 0, 0))
            else:
                index_dict[(name, typ)] = index._is_up, i

        free = [(index, i, 0) for i, index in enumerate(indices) if free[i]]
        free.sort()
        return free, dum

    @staticmethod
    def mul(f, g):
        """
        The algorithms performing the multiplication of two TIDS instances.

        In short, it forms a new TIDS object, joining components and indices,
        checking that abstract indices are compatible, and possibly contracting
        them.

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, TIDS, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> m0, m1, m2, m3 = tensor_indices('m0,m1,m2,m3', Lorentz)
        >>> T = tensorhead('T', [Lorentz]*4, [[1]*4])
        >>> A = tensorhead('A', [Lorentz], [[1]])
        >>> tids_1 = TIDS.from_components_and_indices([T], [m0, m1, -m1, m3])
        >>> tids_2 = TIDS.from_components_and_indices([A], [m2])
        >>> tids_1 * tids_2
        TIDS([T(Lorentz,Lorentz,Lorentz,Lorentz), A(Lorentz)],\
            [(m0, 0, 0), (m3, 3, 0), (m2, 0, 1)], [(1, 2, 0, 0)])

        In this case no contraction has been performed.

        >>> tids_3 = TIDS.from_components_and_indices([A], [-m3])
        >>> tids_1 * tids_3
        TIDS([T(Lorentz,Lorentz,Lorentz,Lorentz), A(Lorentz)],\
            [(m0, 0, 0)], [(1, 2, 0, 0), (3, 0, 0, 1)])

        Free indices m3 and -m3 are identified as a contracted couple, and are
        therefore transformed into dummy indices.

        A wrong index construction (for example, trying to contract two
        contravariant indices or using indices multiple times) would result in
        an exception:

        >>> tids_4 = TIDS.from_components_and_indices([A], [m3])
        >>> # This raises an exception:
        >>> # tids_1 * tids_4
        """
        # find out which free indices of f and g are contracted
        free_dict1 = dict([(i.name, (pos, cpos, i)) for i, pos, cpos in f.free])
        free_dict2 = dict([(i.name, (pos, cpos, i)) for i, pos, cpos in g.free])

        free_names = set(free_dict1.keys()) & set(free_dict2.keys())
        # find the new `free` and `dum`
        nc1 = len(f.components)
        dum2 = [(i1, i2, c1 + nc1, c2 + nc1) for i1, i2, c1, c2 in g.dum]
        free1 = [(ind, i, c) for ind, i, c in f.free if ind.name not in free_names]
        free2 = [(ind, i, c + nc1) for ind, i, c in g.free if ind.name not in free_names]
        free = free1 + free2
        dum = f.dum + dum2
        for name in free_names:
            ipos1, cpos1, ind1 = free_dict1[name]
            ipos2, cpos2, ind2 = free_dict2[name]
            cpos2 += nc1
            if ind1._is_up == ind2._is_up:
                raise ValueError('wrong index construction {0}'.format(ind1))
            if ind1._is_up:
                new_dummy = (ipos1, ipos2, cpos1, cpos2)
            else:
                new_dummy = (ipos2, ipos1, cpos2, cpos1)
            dum.append(new_dummy)
        return (f.components + g.components, free, dum)

    def __mul__(self, other):
        return TIDS(*self.mul(self, other))

    def __str__(self):
        return "TIDS({0}, {1}, {2})".format(self.components, self.free, self.dum)

    def __repr__(self):
        return self.__str__()

    def sorted_components(self):
        """
        Returns a TIDS with sorted components

        The sorting is done taking into account the commutation group
        of the component tensors.
        """
        from sympy.combinatorics.permutations import _af_invert
        cv = list(zip(self.components, range(len(self.components))))
        sign = 1
        n = len(cv) - 1
        for i in range(n):
            for j in range(n, i, -1):
                c = cv[j-1][0].commutes_with(cv[j][0])
                if c not in [0, 1]:
                    continue
                if (cv[j-1][0]._types, cv[j-1][0]._name) > \
                        (cv[j][0]._types, cv[j][0]._name):
                    cv[j-1], cv[j] = cv[j], cv[j-1]
                    if c:
                        sign = -sign

        # perm_inv[new_pos] = old_pos
        components = [x[0] for x in cv]
        perm_inv = [x[1] for x in cv]
        perm = _af_invert(perm_inv)
        free = [(ind, i, perm[c]) for ind, i, c in self.free]
        free.sort()
        dum = [(i1, i2, perm[c1], perm[c2]) for i1, i2, c1, c2 in self.dum]
        dum.sort(key=lambda x: components[x[2]].index_types[x[0]])

        return TIDS(components, free, dum), sign

    def canon_args(self):
        """
        Returns ``(g, dummies, msym, v)``, the entries of ``canonicalize``

        see ``canonicalize`` in ``tensor_can.py``
        """
        # to be called after sorted_components
        from sympy.combinatorics.permutations import _af_new
#         types = list(set(self._types))
#         types.sort(key = lambda x: x._name)
        n = self._ext_rank
        g = [None]*n + [n, n+1]
        pos = 0
        vpos = []
        components = self.components
        for t in components:
            vpos.append(pos)
            pos += t._rank
        # ordered indices: first the free indices, ordered by types
        # then the dummy indices, ordered by types and contravariant before
        # covariant
        # g[position in tensor] = position in ordered indices
        for i, (indx, ipos, cpos) in enumerate(self.free):
            pos = vpos[cpos] + ipos
            g[pos] = i
        pos = len(self.free)
        j = len(self.free)
        dummies = []
        prev = None
        a = []
        msym = []
        for ipos1, ipos2, cpos1, cpos2 in self.dum:
            pos1 = vpos[cpos1] + ipos1
            pos2 = vpos[cpos2] + ipos2
            g[pos1] = j
            g[pos2] = j + 1
            j += 2
            typ = components[cpos1].index_types[ipos1]
            if typ != prev:
                if a:
                    dummies.append(a)
                a = [pos, pos + 1]
                prev = typ
                msym.append(typ.metric_antisym)
            else:
                a.extend([pos, pos + 1])
            pos += 2
        if a:
            dummies.append(a)
        numtyp = []
        prev = None
        for t in components:
            if t == prev:
                numtyp[-1][1] += 1
            else:
                prev = t
                numtyp.append([prev, 1])
        v = []
        for h, n in numtyp:
            if h._comm == 0 or h._comm == 1:
                comm = h._comm
            else:
                comm = TensorManager.get_comm(h._comm, h._comm)
            v.append((h._symmetry.base, h._symmetry.generators, n, comm))
        return _af_new(g), dummies, msym, v

    def perm2tensor(self, g, canon_bp=False):
        """
        Returns a `TIDS` instance corresponding to the permutation ``g``

        ``g``  permutation corresponding to the tensor in the representation
        used in canonicalization

        ``canon_bp``   if True, then ``g`` is the permutation
        corresponding to the canonical form of the tensor
        """
        vpos = []
        components = self.components
        pos = 0
        for t in components:
            vpos.append(pos)
            pos += t._rank
        sorted_free = [x[0] for x in self.free]
        sorted_free.sort()
        nfree = len(sorted_free)
        rank = self._ext_rank
        dum = [[None]*4 for i in range((rank - nfree)//2)]
        free = []
        icomp = -1
        for i in range(rank):
            if i in vpos:
                icomp += vpos.count(i)
                pos0 = i
            ipos = i - pos0
            gi = g[i]
            if gi < nfree:
                ind = sorted_free[gi]
                free.append((ind, ipos, icomp))
            else:
                j = gi - nfree
                idum, cov = divmod(j, 2)
                if cov:
                    dum[idum][1] = ipos
                    dum[idum][3] = icomp
                else:
                    dum[idum][0] = ipos
                    dum[idum][2] = icomp
        dum = [tuple(x) for x in dum]

        return TIDS(components, free, dum)


@doctest_depends_on(modules=('numpy',))
class VTIDS(TIDS):
    """
    This class handles a ``VTIDS`` object, which is a ``TIDS`` object with an
    attached ``numpy`` ``ndarray``.

    To create a `TIDS` object via the standard constructor, the required
    arguments are

    ``components``  `TensorHead` objects representing the components
                    of the tensor expression.

    ``free``        Free indices in their internal representation.

    ``dum``         Dummy indices in their internal representation.

    ``data``        Data as a ``numpy`` ``ndarray``.

    Examples
    ========

    >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, VTIDS, tensorhead
    >>> import numpy
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> m0, m1, m2, m3 = tensor_indices('m0,m1,m2,m3', Lorentz)
    >>> T = tensorhead('T', [Lorentz]*4, [[1]*4])
    >>> data = numpy.array([2,9,6,-5]).reshape(2, 2)
    >>> VTIDS([T], [(m0, 0, 0), (m3, 3, 0)], [(1, 2, 0, 0)], data)
    VTIDS([T(Lorentz,Lorentz,Lorentz,Lorentz)], [(m0, 0, 0), (m3, 3, 0)], [(1, 2, 0, 0)], [[ 2  9]
     [ 6 -5]])

    """

    def __init__(self, components, free, dum, data):
        super(VTIDS, self).__init__(components, free, dum)
        self.data = data

    @staticmethod
    def _contract_ndarray(free1, free2, ndarray1, ndarray2):
        numpy = import_module('numpy')
        self_free = [_[0] for _ in free1]
        axes1 = []
        axes2 = []
        for jpos, jindex in enumerate(free2):
            if -jindex[0] in self_free:
                nidx = self_free.index(-jindex[0])
            else:
                continue
            axes1.append(nidx)
            axes2.append(nidx)

        contracted_ndarray = numpy.tensordot(
            ndarray1,
            ndarray2,
            (axes1, axes2)
        )
        return contracted_ndarray

    @staticmethod
    def mul(f, g):
        """
        Multiplies two ``VTIDS`` objects, it first calls its super method
        on ``TIDS``, then creates a new ``VTIDS`` object, adding ``ndarray``
        data according to the metric contractions of indices.
        """
        components, free, dum = TIDS.mul(f, g)
        data = VTIDS._contract_ndarray(f.free, g.free, f.data, g.data)
        return components, free, dum, data

    def __mul__(f, g):
        return VTIDS(*VTIDS.mul(f, g))

    def correct_signature_from_indices(self, data, indices, free, dum):
        """
        Utility function to correct the values inside the data ndarray
        according to whether indices are covariant or contravariant.

        It uses the metric matrix to lower values of covariant indices.
        """
        numpy = import_module('numpy')
        # change the ndarray values according covariantness/contravariantness of the indices
        # use the metric
        for i, indx in enumerate(indices):
            if not indx.is_up:
                data = numpy.tensordot(
                        indx._tensortype.data,
                        data,
                        (1, i))
                data = numpy.rollaxis(data, i)

        if len(dum) > 0:
            ### perform contractions ###
            axes1 = []
            axes2 = []
            for i, indx1 in enumerate(indices):
                try:
                    nd = indices[:i].index(-indx1)
                except ValueError:
                    continue
                axes1.append(nd)
                axes2.append(i)

            for ax1, ax2 in zip(axes1, axes2):
                data = numpy.trace(data, axis1=ax1, axis2=ax2)
        self.data = data

    @staticmethod
    @doctest_depends_on(modules=('numpy',))
    def parse_data(data):
        """
        Transform data to a numpy ndarray.

        Examples
        ========

        >>> from sympy.tensor.tensor import VTIDS
        >>> VTIDS.parse_data([1, 3, -6, 12])
        [1 3 -6 12]

        >>> VTIDS.parse_data([[1, 2], [4, 7]])
        [[1 2]
         [4 7]]
        """
        numpy = import_module('numpy')

        if (numpy is not None) and (not isinstance(data, numpy.ndarray)):
            if len(data) == 2 and hasattr(data[0], '__call__'):

                def fromfunction_sympify(*x):
                    return sympify(data[0](*x))

                data = numpy.fromfunction(fromfunction_sympify, data[1])
            else:
                vsympify = numpy.vectorize(sympify)
                data = vsympify(numpy.array(data))
        return data

    def _sort_data_axes(self, ret):
        numpy = import_module('numpy')

        new_data = self.data.copy()

        old_free = [i[0] for i in self.free]
        new_free = [i[0] for i in ret.free]

        for i in range(len(new_free)):
            for j in range(i, len(old_free)):
                if old_free[j] == new_free[i]:
                    old_free[i], old_free[j] = old_free[j], old_free[i]
                    new_data = numpy.swapaxes(new_data, i, j)
                    break
        return new_data

    def sorted_components(self):
        ret, sign = TIDS.sorted_components(self)
        new_data = self._sort_data_axes(ret)
        vtids = VTIDS(ret.components, ret.free, ret.dum, new_data)
        return vtids, sign

    def perm2tensor(self, g, canon_bp=False):
        ret = TIDS.perm2tensor(self, g, canon_bp)
        new_data = self._sort_data_axes(ret)
        return VTIDS(ret.components, ret.free, ret.dum, new_data)

    def __str__(self):
        return "VTIDS(%s, %s, %s, %s)" % (self.components, self.free, self.dum, self.data)

    def __repr__(self):
        return str(self)


class _TensorManager(object):
    """
    Class to manage tensor properties.

    Notes
    =====

    Tensors belong to tensor commutation groups; each group has a label
    ``comm``; there are predefined labels:

    ``0``   tensors commuting with any other tensor

    ``1``   tensors anticommuting among themselves

    ``2``   tensors not commuting, apart with those with ``comm=0``

    Other groups can be defined using ``set_comm``; tensors in those
    groups commute with those with ``comm=0``; by default they
    do not commute with any other group.
    """
    def __init__(self):
        self._comm_init()

    def _comm_init(self):
        self._comm = [{} for i in range(3)]
        for i in range(3):
            self._comm[0][i] = 0
            self._comm[i][0] = 0
        self._comm[1][1] = 1
        self._comm[2][1] = None
        self._comm[1][2] = None
        self._comm_symbols2i = {0:0, 1:1, 2:2}
        self._comm_i2symbol = {0:0, 1:1, 2:2}

    @property
    def comm(self):
        return self._comm

    def comm_symbols2i(self, i):
        """
        get the commutation group number corresponding to ``i``

        ``i`` can be a symbol or a number or a string

        If ``i`` is not already defined its commutation group number
        is set.
        """
        if i not in self._comm_symbols2i:
            n = len(self._comm)
            self._comm.append({})
            self._comm[n][0] = 0
            self._comm[0][n] = 0
            self._comm_symbols2i[i] = n
            self._comm_i2symbol[n] = i
            return n
        return self._comm_symbols2i[i]

    def comm_i2symbol(self, i):
        """
        Returns the symbol corresponding to the commutation group number.
        """
        return self._comm_i2symbol[i]

    def set_comm(self, i, j, c):
        """
        set the commutation parameter ``c`` for commutation groups ``i, j``

        Parameters
        ==========

        i, j : symbols representing commutation groups

        c  :  group commutation number

        Notes
        =====

        ``i, j`` can be symbols, strings or numbers,
        apart from ``0, 1`` and ``2`` which are reserved respectively
        for commuting, anticommuting tensors and tensors not commuting
        with any other group apart with the commuting tensors.
        For the remaining cases, use this method to set the commutation rules;
        by default ``c=None``.

        The group commutation number ``c`` is assigned in correspondence
        to the group commutation symbols; it can be

        0        commuting

        1        anticommuting

        None     no commutation property

        Examples
        ========

        ``G`` and ``GH`` do not commute with themselves and commute with
        each other; A is commuting.

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead, TensorManager
        >>> Lorentz = TensorIndexType('Lorentz')
        >>> i0,i1,i2,i3,i4 = tensor_indices('i0:5', Lorentz)
        >>> A = tensorhead('A', [Lorentz], [[1]])
        >>> G = tensorhead('G', [Lorentz], [[1]], 'Gcomm')
        >>> GH = tensorhead('GH', [Lorentz], [[1]], 'GHcomm')
        >>> TensorManager.set_comm('Gcomm', 'GHcomm', 0)
        >>> (GH(i1)*G(i0)).canon_bp()
        G(i0)*GH(i1)
        >>> (G(i1)*G(i0)).canon_bp()
        G(i1)*G(i0)
        >>> (G(i1)*A(i0)).canon_bp()
        A(i0)*G(i1)
        """
        if c not in (0, 1, None):
            raise ValueError('`c` can assume only the values 0, 1 or None')

        if i not in self._comm_symbols2i:
            n = len(self._comm)
            self._comm.append({})
            self._comm[n][0] = 0
            self._comm[0][n] = 0
            self._comm_symbols2i[i] = n
            self._comm_i2symbol[n] = i
        if j not in self._comm_symbols2i:
            n = len(self._comm)
            self._comm.append({})
            self._comm[0][n] = 0
            self._comm[n][0] = 0
            self._comm_symbols2i[j] = n
            self._comm_i2symbol[n] = j
        ni = self._comm_symbols2i[i]
        nj = self._comm_symbols2i[j]
        self._comm[ni][nj] = c
        self._comm[nj][ni] = c

    def set_comms(self, *args):
        """
        set the commutation group numbers ``c`` for symbols ``i, j``

        Parameters
        ==========

        args : sequence of ``(i, j, c)``
        """
        for i, j, c in args:
            self.set_comm(i, j, c)

    def get_comm(self, i, j):
        """
        Return the commutation parameter for commutation group numbers ``i, j``

        see ``_TensorManager.set_comm``
        """
        return self._comm[i].get(j, 0 if i == 0 or j == 0 else None)

    def clear(self):
        """
        Clear the TensorManager.
        """
        self._comm_init()


TensorManager = _TensorManager()


@doctest_depends_on(modules=('numpy',))
class TensorIndexType(Basic):
    """
    A TensorIndexType is characterized by its name and its metric.

    Parameters
    ==========

    name : name of the tensor type

    metric : metric symmetry or metric object or ``None``


    dim : dimension, it can be a symbol or an integer or ``None``

    eps_dim : dimension of the epsilon tensor

    dummy_fmt : name of the head of dummy indices

    Attributes
    ==========

    ``name``
    ``metric_name`` : it is 'metric' or metric.name
    ``metric_antisym``
    ``metric`` : the metric tensor
    ``delta`` : ``Kronecker delta``
    ``epsilon`` : the ``Levi-Civita epsilon`` tensor
    ``dim``
    ``dim_eps``
    ``dummy_fmt``
    ``data`` : a property to add ``ndarray`` values, to work in a specified basis.

    Notes
    =====

    The ``metric`` parameter can be:
    ``metric = False`` symmetric metric (in Riemannian geometry)

    ``metric = True`` antisymmetric metric (for spinor calculus)

    ``metric = None``  there is no metric

    ``metric`` can be an object having ``name`` and ``antisym`` attributes.


    If there is a metric the metric is used to raise and lower indices.

    In the case of antisymmetric metric, the following raising and
    lowering conventions will be adopted:

    ``psi(a) = g(a, b)*psi(-b); chi(-a) = chi(b)*g(-b, -a)``

    ``g(-a, b) = delta(-a, b); g(b, -a) = -delta(a, -b)``

    where ``delta(-a, b) = delta(b, -a)`` is the ``Kronecker delta``
    (see ``TensorIndex`` for the conventions on indices).

    If there is no metric it is not possible to raise or lower indices;
    e.g. the index of the defining representation of ``SU(N)``
    is 'covariant' and the conjugate representation is
    'contravariant'; for ``N > 2`` they are linearly independent.

    ``eps_dim`` is by default equal to ``dim``, if the latter is an integer;
    else it can be assigned (for use in naive dimensional regularization);
    if ``eps_dim`` is not an integer ``epsilon`` is ``None``.

    Examples
    ========

    >>> from sympy.tensor.tensor import TensorIndexType
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> Lorentz.metric
    metric(Lorentz,Lorentz)

    Examples with metric data added, this means it is working on a fixed basis:

    >>> Lorentz.data = [1, -1, -1, -1]
    >>> Lorentz
    TensorIndexType(Lorentz, 0)
    >>> Lorentz.data
    [[1 0 0 0]
    [0 -1 0 0]
    [0 0 -1 0]
    [0 0 0 -1]]
    """

    def __new__(cls, name, metric=False, dim=None, eps_dim=None,
                dummy_fmt=None):

        if isinstance(name, string_types):
            name = Symbol(name)
        obj = Basic.__new__(cls, name, S.One if metric else S.Zero)
        obj._name = str(name)
        if not dummy_fmt:
            obj._dummy_fmt = '%s_%%d' % obj.name
        else:
            obj._dummy_fmt = '%s_%%d' % dummy_fmt
        if metric is None:
            obj.metric_antisym = None
            obj.metric = None
        else:
            if metric in (True, False, 0, 1):
                metric_name = 'metric'
                obj.metric_antisym = metric
            else:
                metric_name = metric.name
                obj.metric_antisym = metric.antisym
            sym2 = TensorSymmetry(get_symmetric_group_sgs(2, obj.metric_antisym))
            S2 = TensorType([obj]*2, sym2)
            obj.metric = S2(metric_name)

        obj._dim = dim
        obj._delta = obj.get_kronecker_delta()
        obj._eps_dim = eps_dim if eps_dim else dim
        obj._epsilon = obj.get_epsilon()
        obj._data = None
        return obj

    @property
    def data(self):
            return self._data

    @data.setter
    def data(self, data):
        numpy = import_module('numpy')
        data = VTIDS.parse_data(data)
        if data.ndim > 2:
            raise ValueError("data have to be of rank 1 (diagonal metric) or 2.")
        if data.ndim == 1:
            if self.dim is not None:
                nda_dim = data.shape[0]
                if nda_dim != self.dim:
                    raise ValueError("Dimension mismatch")

            dim = data.shape[0]
            newndarray = numpy.zeros((dim, dim), dtype=object)
            for i, val in enumerate(data):
                newndarray[i, i] = val
            data = newndarray
        dim1, dim2 = data.shape
        if dim1 != dim2:
            raise ValueError("Non-square matrix tensor.")
        if self.dim is not None:
            if self.dim != dim1:
                raise ValueError("Dimension mismatch")
        self._data = data
        self.metric.data = data

    @data.deleter
    def data(self):
        del self._data
        del self.metric.data

    @property
    def name(self):
        return self._name

    @property
    def dim(self):
        return self._dim

    @property
    def delta(self):
        return self._delta

    @property
    def eps_dim(self):
        return self._eps_dim

    @property
    def epsilon(self):
        return self._epsilon

    @property
    def dummy_fmt(self):
        return self._dummy_fmt

    def get_kronecker_delta(self):
        sym2 = TensorSymmetry(get_symmetric_group_sgs(2))
        S2 = TensorType([self]*2, sym2)
        delta = S2('KD')
        return delta

    def get_epsilon(self):
        if not isinstance(self._eps_dim, int):
            return None
        sym = TensorSymmetry(get_symmetric_group_sgs(self._eps_dim, 1))
        Sdim = TensorType([self]*self._eps_dim, sym)
        epsilon = Sdim('Eps')
        return epsilon

    def __lt__(self, other):
        return self.name < other.name

    def __str__(self):
        return self.name

    __repr__ = __str__


@doctest_depends_on(modules=('numpy',))
class TensorIndex(Basic):
    """
    Represents an abstract tensor index.

    Parameters
    ==========

    name : name of the index
    tensortype : ``TensorIndexType`` of the index
    is_up :  flag for contravariant index

    Attributes
    ==========

    ``name``
    ``tensortype``
    ``is_up``

    Notes
    =====

    Tensor indices are contracted with the Einstein summation convention.

    An index can be in contravariant or in covariant form; in the latter
    case it is represented prepending a ``-`` to the index name.

    Dummy indices have a name with head given by ``tensortype._dummy_fmt``


    Examples
    ========

    >>> from sympy.tensor.tensor import TensorIndexType, TensorIndex, TensorSymmetry, TensorType, get_symmetric_group_sgs
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> i = TensorIndex('i', Lorentz); i
    i
    >>> sym1 = TensorSymmetry(*get_symmetric_group_sgs(1))
    >>> S1 = TensorType([Lorentz], sym1)
    >>> A, B = S1('A,B')
    >>> A(i)*B(-i)
    A(L_0)*B(-L_0)
    """
    def __new__(cls, name, tensortype, is_up=True):
        if isinstance(name, string_types):
            name_symbol = Symbol(name)
        elif isinstance(name, Symbol):
            name_symbol = name
        else:
            raise ValueError("invalid name")

        obj = Basic.__new__(cls, name_symbol, tensortype, S.One if is_up else S.Zero)
        obj._name = str(name)
        obj._tensortype = tensortype
        obj._is_up = is_up
        return obj

    @property
    def name(self):
        return self._name

    @property
    def tensortype(self):
        return self._tensortype

    @property
    def is_up(self):
        return self._is_up

    def _pretty(self):
        s = self._name
        if not self._is_up:
            s = '-%s' % s
        return s

    def __lt__(self, other):
        return (self._tensortype, self._name) < (other._tensortype, other._name)

    def __neg__(self):
        t1 = TensorIndex(self._name, self._tensortype,
                (not self._is_up))
        return t1

def tensor_indices(s, typ):
    """
    Returns list of tensor indices given their names and their types

    Parameters
    ==========

    s : string of comma separated names of indices

    typ : list of ``TensorIndexType`` of the indices

    Examples
    ========

    >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> a, b, c, d = tensor_indices('a,b,c,d', Lorentz)
    """
    if isinstance(s, str):
        a = [x.name for x in symbols(s, seq=True)]
    else:
        raise ValueError('expecting a string')

    tilist = [TensorIndex(i, typ) for i in a]
    if len(tilist) == 1:
        return tilist[0]
    return tilist


@doctest_depends_on(modules=('numpy',))
class TensorSymmetry(Basic):
    """
    Monoterm symmetry of a tensor

    Parameters
    ==========

    bsgs : tuple ``(base, sgs)`` BSGS of the symmetry of the tensor

    Attributes
    ==========

    ``base`` : base of the BSGS
    ``generators`` : generators of the BSGS
    ``rank`` : rank of the tensor

    Notes
    =====

    A tensor can have an arbitrary monoterm symmetry provided by its BSGS.
    Multiterm symmetries, like the cyclic symmetry of the Riemann tensor,
    are not covered.

    See Also
    ========

    sympy.combinatorics.tensor_can.get_symmetric_group_sgs

    Examples
    ========

    Define a symmetric tensor

    >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, TensorSymmetry, TensorType, get_symmetric_group_sgs
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> sym2 = TensorSymmetry(get_symmetric_group_sgs(2))
    >>> S2 = TensorType([Lorentz]*2, sym2)
    >>> V = S2('V')
    """
    def __new__(cls, *args, **kw_args):
        if len(args) == 1:
            base, generators = args[0]
        elif len(args) == 2:
            base, generators = args
        else:
            raise TypeError("bsgs required, either two separate parameters or one tuple")

        if not isinstance(base, Tuple):
            base = Tuple(*base)
        if not isinstance(generators, Tuple):
            generators = Tuple(*generators)
        obj = Basic.__new__(cls, base, generators, **kw_args)
        return obj

    @property
    def base(self):
        return self.args[0]

    @property
    def generators(self):
        return self.args[1]

    @property
    def rank(self):
        return self.args[1][0].size - 2

#    def _hashable_content(self):
#        r = (tuple(self.base), tuple(self.generators))
#        return r


def tensorsymmetry(*args):
    """
    Return a ``TensorSymmetry`` object.

    One can represent a tensor with any monoterm slot symmetry group
    using a BSGS.

    ``args`` can be a BSGS
    ``args[0]``    base
    ``args[1]``    sgs

    Usually tensors are in (direct products of) representations
    of the symmetric group;
    ``args`` can be a list of lists representing the shapes of Young tableaux

    Notes
    =====

    For instance:
    ``[[1]]``       vector
    ``[[1]*n]``     symmetric tensor of rank ``n``
    ``[[n]]``       antisymmetric tensor of rank ``n``
    ``[[2, 2]]``    monoterm slot symmetry of the Riemann tensor
    ``[[1],[1]]``   vector*vector
    ``[[2],[1],[1]`` (antisymmetric tensor)*vector*vector

    Notice that with the shape ``[2, 2]`` we associate only the monoterm
    symmetries of the Riemann tensor; this is an abuse of notation,
    since the shape ``[2, 2]`` corresponds usually to the irreducible
    representation characterized by the monoterm symmetries and by the
    cyclic symmetry.

    Examples
    ========

    Symmetric tensor using a Young tableau

    >>> from sympy.tensor.tensor import TensorIndexType, TensorType, tensorsymmetry
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> sym2 = tensorsymmetry([1, 1])
    >>> S2 = TensorType([Lorentz]*2, sym2)
    >>> V = S2('V')

    Symmetric tensor using a BSGS
    >>> from sympy.tensor.tensor import TensorSymmetry, get_symmetric_group_sgs
    >>> sym2 = tensorsymmetry(*get_symmetric_group_sgs(2))
    >>> S2 = TensorType([Lorentz]*2, sym2)
    >>> V = S2('V')
    """
    from sympy.combinatorics import Permutation

    def tableau2bsgs(a):
        if len(a) == 1:
            # antisymmetric vector
            n = a[0]
            bsgs = get_symmetric_group_sgs(n, 1)
        else:
            if all(x == 1 for x in a):
                # symmetric vector
                n = len(a)
                bsgs = get_symmetric_group_sgs(n)
            elif a == [2, 2]:
                bsgs = riemann_bsgs
            else:
                raise NotImplementedError
        return bsgs

    if not args:
        return TensorSymmetry(Tuple(), Tuple(Permutation(1)))

    if len(args) == 2 and isinstance(args[1][0], Permutation):
        return TensorSymmetry(args)
    base, sgs = tableau2bsgs(args[0])
    for a in args[1:]:
        basex, sgsx = tableau2bsgs(a)
        base, sgs = bsgs_direct_product(base, sgs, basex, sgsx)
    return TensorSymmetry(Tuple(base, sgs))


@doctest_depends_on(modules=('numpy',))
class TensorType(Basic):
    """
    Class of tensor types.

    Parameters
    ==========

    index_types : list of ``TensorIndexType`` of the tensor indices
    symmetry : ``TensorSymmetry`` of the tensor

    Attributes
    ==========

    ``index_types``
    ``symmetry``
    ``types`` : list of ``TensorIndexType`` without repetitions

    Examples
    ========

    Define a symmetric tensor

    >>> from sympy.tensor.tensor import TensorIndexType, tensorsymmetry, TensorType
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> sym2 = tensorsymmetry([1, 1])
    >>> S2 = TensorType([Lorentz]*2, sym2)
    >>> V = S2('V')
    """
    is_commutative = False

    def __new__(cls, index_types, symmetry, **kw_args):
        assert symmetry.rank == len(index_types)
        obj = Basic.__new__(cls, Tuple(*index_types), symmetry, **kw_args)
        return obj

    @property
    def index_types(self):
        return self.args[0]

    @property
    def symmetry(self):
        return self.args[1]

    @property
    def types(self):
        return sorted(set(self.index_types), key=lambda x: x.name)

    def __str__(self):
        return 'TensorType(%s)' % ([str(x) for x in self.index_types])

    def __call__(self, s, comm=0):
        """
        Return a TensorHead object or a list of TensorHead objects.

        ``s``  name or string of names

        ``comm``: commutation group number
        see ``_TensorManager.set_comm``

        Examples
        ========

        Define symmetric tensors ``V``, ``W`` and ``G``, respectively
        commuting, anticommuting and with no commutation symmetry

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorsymmetry, TensorType, canon_bp
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> a, b = tensor_indices('a,b', Lorentz)
        >>> sym2 = tensorsymmetry([1]*2)
        >>> S2 = TensorType([Lorentz]*2, sym2)
        >>> V = S2('V')
        >>> W = S2('W', 1)
        >>> G = S2('G', 2)
        >>> canon_bp(V(a, b)*V(-b, -a))
        V(L_0, L_1)*V(-L_0, -L_1)
        >>> canon_bp(W(a, b)*W(-b, -a))
        0
        """
        if isinstance(s, str):
            names = [x.name for x in symbols(s, seq=True)]
        else:
            raise ValueError('expecting a string')
        if len(names) == 1:
            return TensorHead(names[0], self, comm)
        else:
            return [TensorHead(name, self, comm) for name in names]

def tensorhead(name, typ, sym, comm=0):
    """
    Function generating tensorhead(s).

    Parameters
    ==========

    name : name or sequence of names (as in ``symbol``)

    typ :  index types

    sym :  same as ``*args`` in ``tensorsymmetry``

    comm : commutation group number
    see ``_TensorManager.set_comm``


    Examples
    ========

    >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> a, b = tensor_indices('a,b', Lorentz)
    >>> A = tensorhead('A', [Lorentz]*2, [[1]*2])
    >>> A(a, -b)
    A(a, -b)

    """
    sym = tensorsymmetry(*sym)
    S = TensorType(typ, sym)
    return S(name, comm)


@doctest_depends_on(modules=('numpy',))
class TensorHead(Basic):
    """
    Tensor head of the tensor

    Parameters
    ==========

    name : name of the tensor

    typ : list of TensorIndexType

    comm : commutation group number

    Attributes
    ==========

    ``name``
    ``index_types``
    ``rank``
    ``types``  :  equal to ``typ.types``
    ``symmetry`` : equal to ``typ.symmetry``
    ``comm`` : commutation group

    Notes
    =====

    A ``TensorHead`` belongs to a commutation group, defined by a
    symbol on number ``comm`` (see ``_TensorManager.set_comm``);
    tensors in a commutation group have the same commutation properties;
    by default ``comm`` is ``0``, the group of the commuting tensors.

    Examples
    ========

    >>> from sympy.tensor.tensor import TensorIndexType, tensorsymmetry, TensorType
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> sym2 = tensorsymmetry([1]*2)
    >>> S2 = TensorType([Lorentz]*2, sym2)
    >>> A = S2('A')

    Examples with ndarray values:

    >>> from sympy.tensor.tensor import tensor_indices, tensorhead
    >>> Lorentz.data = [1, -1, -1, -1]
    >>> i0, i1 = tensor_indices('i0:2', Lorentz)
    >>> A.data = [[j+2*i for j in range(4)] for i in range(4)]

    in order to retrieve data, it is also necessary to specify abstract indices
    enclosed by round brackets, then numerical indices inside square brackets.

    >>> A(i0, i1)[0, 0]
    0
    >>> A(i0, i1)[2, 3] == 3+2*2
    True

    Notice that square brackets create a valued tensor expression instance:

    >>> A(i0, i1)
    A(i0, i1)

    To view the data, just type:

    >>> A.data
    [[0 1 2 3]
     [2 3 4 5]
     [4 5 6 7]
     [6 7 8 9]]

    Turning to a tensor expression, covariant indices get the corresponding
    data corrected by the metric:

    >>> A(i0, -i1).data
    [[0 -1 -2 -3]
     [2 -3 -4 -5]
     [4 -5 -6 -7]
     [6 -7 -8 -9]]

    >>> A(-i0, -i1).data
    [[0 -1 -2 -3]
     [-2 3 4 5]
     [-4 5 6 7]
     [-6 7 8 9]]

    while if all indices are contravariant, the ``ndarray`` remains the same

    >>> A(i0, i1).data
     [[0 1 2 3]
     [2 3 4 5]
     [4 5 6 7]
     [6 7 8 9]]

    When all indices are contracted and data are added to the tensor,
    it will return a scalar resulting from all contractions:

    >>> A(i0, -i0)
    -18

    """
    is_commutative = False

    def __new__(cls, name, typ, comm=0, **kw_args):
        if isinstance(name, string_types):
            name_symbol = Symbol(name)
        elif isinstance(name, Symbol):
            name_symbol = name
        else:
            raise ValueError("invalid name")

        comm2i = TensorManager.comm_symbols2i(comm)

        obj = Basic.__new__(cls, name_symbol, typ, **kw_args)
        obj._name = obj.args[0].name
        obj._rank = len(obj.index_types)
        obj._types = typ.types
        obj._symmetry = typ.symmetry
        obj._comm = comm2i
        obj._data = None
        return obj

    @property
    def name(self):
        return self._name

    @property
    def rank(self):
        return self._rank

    @property
    def types(self):
        return self._types[:]

    @property
    def symmetry(self):
        return self._symmetry

    @property
    def typ(self):
        return self.args[1]

    @property
    def comm(self):
        return self._comm

    @property
    def index_types(self):
        return self.args[1].index_types[:]

    def __lt__(self, other):
        return (self.name, self.index_types) < (other.name, other.index_types)

#    def _hashable_content(self):
#        r = (self._name, tuple(self._types), self._symmetry, self._comm)
#        return r

    def commutes_with(self, other):
        """
        Returns ``0`` if ``self`` and ``other`` commute, ``1`` if they anticommute.

        Returns ``None`` if ``self`` and ``other`` neither commute nor anticommute.
        """
        r = TensorManager.get_comm(self._comm, other._comm)
        return r

    def _pretty(self):
        return '%s(%s)' %(self.name, ','.join([str(x) for x in self.index_types]))

    def __call__(self, *indices):
        """
        Returns a tensor with indices.

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> a, b = tensor_indices('a,b', Lorentz)
        >>> A = tensorhead('A', [Lorentz]*2, [[1]*2])
        >>> t = A(a, -b)
        """
        if not Tuple(*[indices[i]._tensortype for i in range(len(indices))]) == self.index_types:
            raise ValueError('wrong index type')
        components = [self]
        tids = TIDS.from_components_and_indices(components, indices)

        if self.data is not None:
            tids = VTIDS(tids.components, tids.free, tids.dum, self.data)
            tids.correct_signature_from_indices(self.data, indices, tids.free, tids.dum)
            numpy = import_module('numpy')
            if not isinstance(tids.data, numpy.ndarray):
                return tids.data

        return TensMul.from_TIDS(S.One, tids)

    def __pow__(self, other):
        if self.data is None:
            raise ValueError("No power on abstract tensors.")
        numpy = import_module('numpy')
        metrics = [_.data for _ in self.args[1].args[0]]

        marray = self.data
        for metric in metrics:
            marray = numpy.tensordot(marray, numpy.tensordot(metric, marray, (1, 0)), (0, 0))
        pow2 = marray[()]
        return pow2 ** (Rational(1, 2) * other)

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, data):
        data = VTIDS.parse_data(data)
        for dim, indextype in zip(data.shape, self.index_types):
            if indextype.dim is None:
                continue
            if dim != indextype.dim:
                raise ValueError("wrong dimension of ndarray")
        self._data = data

    @data.deleter
    def data(self):
        del self._data

    def applyfunc(self, func):
        th = TensorHead(*self.args)
        th.data = func(self.data)
        return th

    def __iter__(self):
        return self.data.flatten().__iter__()

    def strip(self):
        """
        Return an identical ``TensorHead``, just with ``ndarray`` data removed.
        """
        return TensorHead(*self.args)


@doctest_depends_on(modules=('numpy',))
class TensExpr(Basic):
    """
    Abstract base class for tensor expressions

    Notes
    =====

    A tensor expression is an expression formed by tensors;
    currently the sums of tensors are distributed.

    A ``TensExpr`` can be a ``TensAdd`` or a ``TensMul``.

    ``TensAdd`` objects are put in canonical form using the Butler-Portugal
    algorithm for canonicalization under monoterm symmetries.

    ``TensMul`` objects are formed by products of component tensors,
    and include a coefficient, which is a SymPy expression.


    In the internal representation contracted indices are represented
    by ``(ipos1, ipos2, icomp1, icomp2)``, where ``icomp1`` is the position
    of the component tensor with contravariant index, ``ipos1`` is the
    slot which the index occupies in that component tensor.

    Contracted indices are therefore nameless in the internal representation.
    """

    _op_priority = 11.0
    is_commutative = False

    def __neg__(self):
        return self*S.NegativeOne

    def __abs__(self):
        raise NotImplementedError

    def __add__(self, other):
        raise NotImplementedError

    def __radd__(self, other):
        raise NotImplementedError

    def __sub__(self, other):
        raise NotImplementedError

    def __rsub__(self, other):
        raise NotImplementedError

    def __mul__(self, other):
        raise NotImplementedError

    def __rmul__(self, other):
        raise NotImplementedError

    def __pow__(self, other):
        if self.data is None:
            raise ValueError("No power without ndarray data.")
        numpy = import_module('numpy')
        free = self.free

        marray = self.data
        for metric in free:
            marray = numpy.tensordot(
                marray,
                numpy.tensordot(
                    metric[0]._tensortype.data,
                    marray,
                    (1, 0)
                ),
                (0, 0)
            )
        pow2 = marray[()]
        return pow2 ** (Rational(1, 2) * other)

    def __rpow__(self, other):
        raise NotImplementedError

    def __div__(self, other):
        raise NotImplementedError

    def __rdiv__(self, other):
        raise NotImplementedError()

    __truediv__ = __div__
    __rtruediv__ = __rdiv__

    @doctest_depends_on(modules=('numpy',))
    def get_matrix(self):
        """
        Returns ndarray data as a matrix, if data are available and ndarray
        dimension does not exceed 2.

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensorsymmetry, TensorType
        >>> from sympy import ones
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> sym2 = tensorsymmetry([1]*2)
        >>> S2 = TensorType([Lorentz]*2, sym2)
        >>> A = S2('A')

        >>> from sympy.tensor.tensor import tensor_indices, tensorhead
        >>> Lorentz.data = [1, -1, -1, -1]
        >>> i0, i1 = tensor_indices('i0:2', Lorentz)
        >>> A.data = [[j+2*i for j in range(4)] for i in range(4)]
        >>> A(i0, i1).get_matrix()
         Matrix([
        [0, 1, 2, 3],
        [2, 3, 4, 5],
        [4, 5, 6, 7],
        [6, 7, 8, 9]])

        It is possible to perform usual operation on matrices, such as the
        matrix multiplication:

        >>> A(i0, i1).get_matrix()*ones(4, 1)
        Matrix([
        [ 6],
        [14],
        [22],
        [30]])
        """
        if 0 < self.rank <= 2:
            rows = self.data.shape[0]
            columns = self.data.shape[1] if self.rank == 2 else 1
            if self.rank == 2:
                mat_list = [] * rows
                for i in range(rows):
                    mat_list.append([])
                    for j in range(columns):
                        mat_list[i].append(self[i, j])
            else:
                mat_list = [None] * rows
                for i in range(rows):
                    mat_list[i] = self[i]
            return Matrix(mat_list)
        else:
            raise NotImplementedError(
                "missing multidimensional reduction to matrix.")

    def _eval_simplify(self, ratio, measure):
        # this is a way to simplify a tensor expression.

        # This part walks for all `TensorHead`s appearing in the tensor expr
        # and looks for `simplify_this_type`, to specifically act on a subexpr
        # containing one type of `TensorHead` instance only:
        expr = self
        for i in list(set(self.components)):
            if hasattr(i, 'simplify_this_type'):
                expr = i.simplify_this_type(expr)

        # TODO: missing feature, perform metric contraction.

        return expr

    def strip(self):
        """
        Return an identical tensor expression, just with ``ndarray`` data removed.
        """
        return self.func(*self.args)


@doctest_depends_on(modules=('numpy',))
class TensAdd(TensExpr):
    """
    Sum of tensors

    Parameters
    ==========

    free_args : list of the free indices

    Attributes
    ==========

    ``args`` : tuple of addends
    ``rank`` : rank of the tensor
    ``free_args`` : list of the free indices in sorted order

    Notes
    =====

    Sum of more than one tensor are put automatically in canonical form.

    Examples
    ========

    >>> from sympy.tensor.tensor import TensorIndexType, tensorhead, tensor_indices
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> a, b = tensor_indices('a,b', Lorentz)
    >>> p, q = tensorhead('p,q', [Lorentz], [[1]])
    >>> t = p(a) + q(a); t
    p(a) + q(a)
    >>> t(b)
    p(b) + q(b)

    Examples with data added to the tensor expression:

    >>> from sympy import eye
    >>> Lorentz.data = [1, -1, -1, -1]
    >>> a, b = tensor_indices('a, b', Lorentz)
    >>> p.data = [2, 3, -2, 7]
    >>> q.data = [2, 3, -2, 7]
    >>> t = p(a) + q(a); t
    p(a) + q(a)

    >>> t(b)
    p(b) + q(b)

    The following are: 2**2 - 3**2 - 2**2 - 7**2 ==> -58

    >>> p(a)*p(-a)
    -58

    >>> p(a)**2
    -58
    """

    def __new__(cls, *args, **kw_args):
        old_args = args[:]
        args = [sympify(x) for x in args if x]
        args, data = TensAdd._tensAdd_flatten(args)

        if not args:
            return S.Zero

        TensAdd._tensAdd_check(args)
        args = Tuple(*args)

        # if TensAdd has only 1 TensMul element in its `args`:
        if len(args) == 1 and isinstance(args[0], TensMul):
            obj = Basic.__new__(cls, *args, **kw_args)
            obj._data = data
    #        obj._args = tuple(a)
            return obj

        # canonicalize all TensMul
        args = [x.canon_bp() for x in args if x]
        args = [x for x in args if x]

        # if there are no more args (i.e. have cancelled out),
        # just return zero:
        if not args:
            return S.Zero

        # collect canonicalized terms
        args.sort(key=lambda x: (x.components, x.free, x.dum))
        a = TensAdd._tensAdd_collect_terms(args)
        if not a:
            return S.Zero
        # it there is only a component tensor return it
        if len(a) == 1:
            if data is not None:
                a[0].data = old_args[0].data
            return a[0]

        args = Tuple(*args)
        obj = Basic.__new__(cls, *args, **kw_args)
        obj._args = tuple(a)
        obj._data = data
        return obj

    @staticmethod
    def _tensAdd_flatten(args):
        """
        flatten TensAdd, coerce terms which are not tensors to tensors
        """
        data_list = []

        if not all(isinstance(x, TensExpr) for x in args):
            args1 = []
            for x in args:
                if isinstance(x, TensExpr):
                    if isinstance(x, TensAdd):
                        args1.extend(list(x.args))
                    else:
                        args1.append(x)
            args1 = [x for x in args1 if isinstance(x, TensExpr) and x._coeff]
            args2 = [x for x in args if not isinstance(x, TensExpr)]
            t1 = TensMul.from_data(Add(*args2), [], [], [])
            args = [t1] + args1
        a = []
        for x in args:
            data_list.append(x.data)
            if isinstance(x, TensAdd):
                a.extend(list(x.args))
            else:
                a.append(x)

        data_p = [_ is None for _ in data_list]
        data = None
        if data_p:
            if any(data_p) != all(data_p):
                raise ValueError("attempting to mix tensors with data and tensors without data")

            if not any(data_p):
                data = S.Zero
                for i in args:
                    if isinstance(i, TensAdd):
                        data += i.data
                    else:
                        data += i.coeff * i.data
                if not args[0].rank:  # autodrop point
                    return data

        args = [x for x in a if x._coeff]
        return args, data

    @staticmethod
    def _tensAdd_check(args):
        # check that all addends have the same free indices
        indices0 = sorted([x[0] for x in args[0].free], key=lambda x: x.name)
        list_indices = [sorted([y[0] for y in x.free], key=lambda x: x.name) for x in args[1:]]
        if not all(x == indices0 for x in list_indices):
            raise ValueError('all tensors must have the same indices')

    @staticmethod
    def _tensAdd_collect_terms(args):
        # collect TensMul terms differing at most by their coefficient
        a = []
        prev = args[0]
        prev_coeff = prev._coeff
        changed = False

        for x in args[1:]:
            # if x and prev have the same tensor, update the coeff of prev
            if x.components == prev.components \
                    and x.free == prev.free and x.dum == prev.dum:
                prev_coeff = prev_coeff + x._coeff
                changed = True
                op = 0
            else:
                # x and prev are different; if not changed, prev has not
                # been updated; store it
                if not changed:
                    a.append(prev)
                else:
                    # get a tensor from prev with coeff=prev_coeff and store it
                    if prev_coeff:
                        t = TensMul.from_data(prev_coeff, prev.components,
                            prev.free, prev.dum)
                        a.append(t)
                # move x to prev
                op = 1
                pprev, prev = prev, x
                pprev_coeff, prev_coeff = prev_coeff, x._coeff
                changed = False
        # if the case op=0 prev was not stored; store it now
        # in the case op=1 x was not stored; store it now (as prev)
        if op == 0 and prev_coeff:
            prev = TensMul.from_data(prev_coeff, prev.components, prev.free, prev.dum)
            a.append(prev)
        elif op == 1:
            a.append(prev)
        return a

    @property
    def rank(self):
        return self.args[0].rank

    @property
    def free_args(self):
        return self.args[0].free_args

    def __call__(self, *indices):
        """Returns tensor with ordered free indices replaced by ``indices``

        Parameters
        ==========

        indices

        Examples
        ========

        >>> from sympy import Symbol
        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> D = Symbol('D')
        >>> Lorentz = TensorIndexType('Lorentz', dim=D, dummy_fmt='L')
        >>> i0,i1,i2,i3,i4 = tensor_indices('i0:5', Lorentz)
        >>> p, q = tensorhead('p,q', [Lorentz], [[1]])
        >>> g = Lorentz.metric
        >>> t = p(i0)*p(i1) + g(i0,i1)*q(i2)*q(-i2)
        >>> t(i0,i2)
        metric(i0, i2)*q(L_0)*q(-L_0) + p(i0)*p(i2)
        >>> t(i0,i1) - t(i1,i0)
        0
        """
        free_args = self.free_args
        indices = list(indices)
        if [x._tensortype for x in indices] != [x._tensortype for x in free_args]:
            raise ValueError('incompatible types')
        if indices == free_args:
            return self
        index_tuples = list(zip(free_args, indices))
        a = [x.fun_eval(*index_tuples) for x in self.args]
        res = TensAdd(*a)

        return res

    def canon_bp(self):
        """
        canonicalize using the Butler-Portugal algorithm for canonicalization
        under monoterm symmetries.
        """
        args = [x.canon_bp() for x in self.args]
        res = TensAdd(*args)
        return res

    def equals(self, other):
        other = sympify(other)
        if isinstance(other, TensMul) and other._coeff == 0:
            return all(x._coeff == 0 for x in self.args)
        if isinstance(other, TensExpr):
            if self.rank != other.rank:
                return False
        if isinstance(other, TensAdd):
            if set(self.args) != set(other.args):
                return False
        t = self - other
        if not isinstance(t, TensExpr):
            return t == 0
        else:
            if isinstance(t, TensMul):
                return t._coeff == 0
            else:
                return all(x._coeff == 0 for x in t.args)

    def __eq__(self, other):
        return self.equals(other)

    def __add__(self, other):
        return TensAdd(self, other)

    def __radd__(self, other):
        return TensAdd(other, self)

    def __sub__(self, other):
        return TensAdd(self, -other)

    def __rsub__(self, other):
        return TensAdd(other, -self)

    def __mul__(self, other):
        tadd = TensAdd(*(x*other for x in self.args))
        if not isinstance(tadd, TensExpr):
            if (self.data is not None):
                tadd.data = self.data * other
            return tadd
        if self.data is not None:
            if isinstance(other, TensExpr):
                if other.data is None:
                    raise ValueError("Cannot multiply abstract and valued tensors.")
                data = VTIDS._contract_ndarray(self.args[0].free,
                                            other.free,
                                            self.data,
                                            other.data)
                if data.ndim == 0:
                    return data[()]
            else:
                data = self.data * other
        else:
            data = None
        tadd.data = data
        return tadd

    def __rmul__(self, other):
        tadd = self*other
        if self.data is not None:
            tadd.data = other*self.data
        return tadd

    def __div__(self, other):
        other = sympify(other)
        if isinstance(other, TensExpr):
            raise ValueError('cannot divide by a tensor')
        tadd = TensAdd(*(x/other for x in self.args))
        if self.data is not None:
            tadd.data = self.data / other
        return tadd

    def __rdiv__(self, other):
        raise ValueError('cannot divide by a tensor')

    def __getitem__(self, item):
        return self.data[item]

    __truediv__ = __div__
    __truerdiv__ = __rdiv__

    def _hashable_content(self):
        return tuple(self.args)

    def __hash__(self):
        return super(TensAdd, self).__hash__()

    def __ne__(self, other):
        return not (self == other)

    def contract_delta(self, delta):
        args = [x.contract_delta(delta) for x in self.args]
        t = TensAdd(*args)
        return canon_bp(t)

    def contract_metric(self, g, contract_all=False):
        """
        Raise or lower indices with the metric ``g``

        Parameters
        ==========

        g :  metric

        contract_all : if True, eliminate all ``g`` which are contracted

        Notes
        =====

        see the ``TensorIndexType`` docstring for the contraction conventions
        """

        args = [x.contract_metric(g, contract_all) for x in self.args]
        t = TensAdd(*args)
        return canon_bp(t)


    def fun_eval(self, *index_tuples):
        """
        Return a tensor with free indices substituted according to ``index_tuples``

        Parameters
        ==========

        index_types : list of tuples ``(old_index, new_index)``

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> i, j, k, l = tensor_indices('i,j,k,l', Lorentz)
        >>> A, B = tensorhead('A,B', [Lorentz]*2, [[1]*2])
        >>> t = A(i, k)*B(-k, -j) + A(i, -j)
        >>> t.fun_eval((i, k),(-j, l))
        A(k, L_0)*B(l, -L_0) + A(k, l)
        """
        args = self.args
        args1 = []
        for x in args:
            y = x.fun_eval(*index_tuples)
            args1.append(y)
        return TensAdd(*args1)

    def substitute_indices(self, *index_tuples):
        """
        Return a tensor with free indices substituted according to ``index_tuples``

        Parameters
        ==========

        index_types : list of tuples ``(old_index, new_index)``

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> i, j, k, l = tensor_indices('i,j,k,l', Lorentz)
        >>> A, B = tensorhead('A,B', [Lorentz]*2, [[1]*2])
        >>> t = A(i, k)*B(-k, -j); t
        A(i, L_0)*B(-L_0, -j)
        >>> t.substitute_indices((i,j), (j, k))
        A(j, L_0)*B(-L_0, -k)
        """
        args = self.args
        args1 = []
        for x in args:
            y = x.substitute_indices(*index_tuples)
            args1.append(y)
        return TensAdd(*args1)

    def _pretty(self):
        a = []
        args = self.args
        for x in args:
            a.append(str(x))
        a.sort()
        s = ' + '.join(a)
        s = s.replace('+ -', '- ')
        return s

    @staticmethod
    def from_TIDS_list(coeff, tids_list):
        """
        Given a list of coefficients and a list of `TIDS` objects, construct
        a `TensAdd` instance, equivalent to the one that would result from
        creating single instances of `TensMul` and then adding them.

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead, TensAdd
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> i, j = tensor_indices('i,j', Lorentz)
        >>> A, B = tensorhead('A,B', [Lorentz]*2, [[1]*2])
        >>> eA = 3*A(i, j)
        >>> eB = 2*B(j, i)
        >>> t1 = eA._tids
        >>> t2 = eB._tids
        >>> c1 = eA.coeff
        >>> c2 = eB.coeff
        >>> TensAdd.from_TIDS_list([c1, c2], [t1, t2])
        2*B(i, j) + 3*A(i, j)

        If the coefficient parameter is a scalar, then it will be applied
        as a coefficient on all `TIDS` objects.

        >>> TensAdd.from_TIDS_list(4, [t1, t2])
        4*A(i, j) + 4*B(i, j)

        """
        if not isinstance(coeff, (list, tuple, Tuple)):
            coeff = [coeff] * len(tids_list)
        tensmul_list = [TensMul.from_TIDS(c, t) for c, t in zip(coeff, tids_list)]
        return TensAdd(*tensmul_list)

    def applyfunc(self, func):
        """
        Return a new ``TensAdd`` object, whose data ndarray will be the elementwise
        map of the current data ndarray by function ``func``.
        """
        new_tadd = TensAdd(*self.args)
        new_tadd.data = func(self.data)
        return new_tadd

    @property
    def data(self):
        if hasattr(self, "_data"):
            return self._data
        return None

    @data.setter
    def data(self, data):
        # TODO: check data compatibility with properties of tensor.
        self._data = data

    @data.deleter
    def data(self):
        del self._data

    def __iter__(self):
        if not self.data:
            raise ValueError("No iteration on abstract tensors")
        return self.data.flatten().__iter__()


@doctest_depends_on(modules=('numpy',))
class TensMul(TensExpr):
    """
    Product of tensors

    Parameters
    ==========

    coeff : SymPy coefficient of the tensor
    args

    Attributes
    ==========

    ``components`` : list of ``TensorHead`` of the component tensors
    ``types`` : list of nonrepeated ``TensorIndexType``
    ``free`` : list of ``(ind, ipos, icomp)``, see Notes
    ``dum`` : list of ``(ipos1, ipos2, icomp1, icomp2)``, see Notes
    ``ext_rank`` : rank of the tensor counting the dummy indices
    ``rank`` : rank of the tensor
    ``coeff`` : SymPy coefficient of the tensor
    ``free_args`` : list of the free indices in sorted order
    ``is_canon_bp`` : ``True`` if the tensor in in canonical form

    Notes
    =====

    ``args[0]``   list of ``TensorHead`` of the component tensors.

    ``args[1]``   list of ``(ind, ipos, icomp)``
    where ``ind`` is a free index, ``ipos`` is the slot position
    of ``ind`` in the ``icomp``-th component tensor.

    ``args[2]`` list of tuples representing dummy indices.
    ``(ipos1, ipos2, icomp1, icomp2)`` indicates that the contravariant
    dummy index is the ``ipos1``-th slot position in the ``icomp1``-th
    component tensor; the corresponding covariant index is
    in the ``ipos2`` slot position in the ``icomp2``-th component tensor.

    """

    def __new__(cls, coeff, *args, **kw_args):
        coeff = sympify(coeff)

        if len(args) == 2:
            components = args[0]
            indices = args[1]
            tids = TIDS.from_components_and_indices(components, indices)
        elif len(args) == 1:
            tids = args[0]
            components = tids.components
            indices = tids.to_indices()
        else:
            raise TypeError("wrong construction")

        for i in indices:
            assert isinstance(i, TensorIndex)

        t_components = Tuple(*components)
        t_indices = Tuple(*indices)

        obj = Basic.__new__(cls, coeff, t_components, t_indices)
        obj._types = []
        for t in tids.components:
            obj._types.extend(t._types)
        obj._tids = tids
        obj._ext_rank = len(obj._tids.free) + 2*len(obj._tids.dum)
        obj._coeff = coeff
        obj._is_canon_bp = kw_args.get('is_canon_bp', False)

        return obj

    @staticmethod
    def from_data(coeff, components, free, dum, data=None, **kw_args):
        if data is None:
            tids = TIDS(components, free, dum)
        else:
            tids = VTIDS(components, free, dum, data)
        return TensMul.from_TIDS(coeff, tids, **kw_args)

    @staticmethod
    def from_TIDS(coeff, tids, **kw_args):
        # t_indices = tids.to_indices()
        if isinstance(tids, VTIDS) and len(tids.free) == 0:  # autodrop point
            return coeff * tids.data[()]
        return TensMul(coeff, tids, **kw_args)

    @property
    def free_args(self):
        return sorted([x[0] for x in self.free])

    @property
    def components(self):
        return self._tids.components[:]

    @property
    def free(self):
        return self._tids.free[:]

    @property
    def coeff(self):
        return self._coeff

    @property
    def dum(self):
        return self._tids.dum[:]

    @property
    def rank(self):
        return len(self.free)

    @property
    def types(self):
        return self._types[:]

    def equals(self, other):
        if other == 0:
            return self._coeff == 0
        other = sympify(other)
        if not isinstance(other, TensExpr):
            assert not self.components
            return self._coeff == other
        res = self - other
        return res == 0

    def _hashable_content(self):
        t = self.canon_bp()
        r = (t._coeff, tuple(t.components), \
                tuple(sorted(t.free)), tuple(sorted(t.dum)))
        return r

    def __hash__(self):
        return super(TensMul, self).__hash__()

    def __eq__(self, other):
        # Basic's equality comparison considers 0 and a zero TensMul
        # as never equal, here is a workaround:
        if other == 0 and self.coeff == 0:
            return True
        return super(TensMul, self).__eq__(other)

    def __ne__(self, other):
        return not self == other

    def get_indices(self):
        """
        Returns the list of indices of the tensor

        The indices are listed in the order in which they appear in the
        component tensors.
        The dummy indices are given a name which does not collide with
        the names of the free indices.

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> m0, m1, m2 = tensor_indices('m0,m1,m2', Lorentz)
        >>> g = Lorentz.metric
        >>> p, q = tensorhead('p,q', [Lorentz], [[1]])
        >>> t = p(m1)*g(m0,m2)
        >>> t.get_indices()
        [m1, m0, m2]
        """
        indices = [None]*self._ext_rank
        start = 0
        pos = 0
        vpos = []
        components = self.components
        for t in components:
            vpos.append(pos)
            pos += t._rank
        cdt = defaultdict(int)
        # if the free indices have names with dummy_fmt, start with an
        # index higher than those for the dummy indices
        # to avoid name collisions
        for indx, ipos, cpos in self.free:
            if indx._name.split('_')[0] == indx._tensortype._dummy_fmt[:-3]:
                cdt[indx._tensortype] = max(cdt[indx._tensortype], int(indx._name.split('_')[1]) + 1)
            start = vpos[cpos]
            indices[start + ipos] = indx
        for ipos1, ipos2, cpos1, cpos2 in self.dum:
            start1 = vpos[cpos1]
            start2 = vpos[cpos2]
            typ1 = components[cpos1].index_types[ipos1]
            assert typ1 == components[cpos2].index_types[ipos2]
            fmt = typ1._dummy_fmt
            nd = cdt[typ1]
            indices[start1 + ipos1] = TensorIndex(fmt % nd, typ1)
            indices[start2 + ipos2] = TensorIndex(fmt % nd, typ1, False)
            cdt[typ1] += 1
        return indices

    def split(self):
        """
        Returns a list of tensors, whose product is ``self``

        Dummy indices contracted among different tensor components
        become free indices with the same name as the one used to
        represent the dummy indices.

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> a, b, c, d = tensor_indices('a,b,c,d', Lorentz)
        >>> A, B = tensorhead('A,B', [Lorentz]*2, [[1]*2])
        >>> t = A(a,b)*B(-b,c)
        >>> t
        A(a, L_0)*B(-L_0, c)
        >>> t.split()
        [A(a, L_0), B(-L_0, c)]
        """
        indices = self.get_indices()
        pos = 0
        components = self.components
        if not components:
            return [TensMul.from_data(self._coeff, [], [], [])]
        res = []
        for t in components:
            t1 = t(*indices[pos:pos + t._rank])
            pos += t._rank
            res.append(t1)
        res[0] = TensMul.from_data(self._coeff, res[0].components, res[0]._tids.free, res[0]._tids.dum, is_canon_bp=res[0]._is_canon_bp)
        return res

    def __add__(self, other):
        return TensAdd(self, other)

    def __radd__(self, other):
        return TensAdd(other, self)

    def __sub__(self, other):
        return TensAdd(self, -other)

    def __rsub__(self, other):
        return TensAdd(other, -self)

    def __mul__(self, other):
        """
        Multiply two tensors using Einstein summation convention.

        If the two tensors have an index in common, one contravariant
        and the other covariant, in their product the indices are summed

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> m0, m1, m2 = tensor_indices('m0,m1,m2', Lorentz)
        >>> g = Lorentz.metric
        >>> p, q = tensorhead('p,q', [Lorentz], [[1]])
        >>> t1 = p(m0)
        >>> t2 = q(-m0)
        >>> t1*t2
        p(L_0)*q(-L_0)
        """
        other = sympify(other)
        if not isinstance(other, TensExpr):
            coeff = self._coeff*other
            return TensMul.from_TIDS(coeff, self._tids, is_canon_bp=self._is_canon_bp)
        if isinstance(other, TensAdd):
            return TensAdd(*[self*x for x in other.args])

        new_tids = self._tids*other._tids
        coeff = self._coeff*other._coeff
        return TensMul.from_TIDS(coeff, new_tids)

    def __rmul__(self, other):
        other = sympify(other)
        coeff = other*self._coeff
        return TensMul.from_TIDS(coeff, self._tids)

    def __div__(self, other):
        other = sympify(other)
        if isinstance(other, TensExpr):
            raise ValueError('cannot divide by a tensor')
        coeff = self._coeff/other
        return TensMul.from_TIDS(coeff, self._tids, is_canon_bp=self._is_canon_bp)

    def __rdiv__(self, other):
        raise ValueError('cannot divide by a tensor')

    def __getitem__(self, item):
        return self.coeff * self.data[item]

    __truediv__ = __div__
    __truerdiv__ = __rdiv__

    def sorted_components(self):
        """
        Returns a tensor with sorted components
        calling the corresponding method in a `TIDS` object.
        """
        new_tids, sign = self._tids.sorted_components()
        coeff = -self._coeff if sign == -1 else self._coeff
        t = TensMul.from_TIDS(coeff, new_tids)
        return t

    def perm2tensor(self, g, canon_bp=False):
        """
        Returns the tensor corresponding to the permutation ``g``

        For further details, see the method in `TIDS` with the same name.
        """
        new_tids = self._tids.perm2tensor(g, canon_bp)
        coeff = self._coeff
        if g[-1] != len(g) - 1:
            coeff = -coeff
        res = TensMul.from_TIDS(coeff, new_tids, is_canon_bp=canon_bp)
        return res

    def canon_bp(self):
        """
        Canonicalize using the Butler-Portugal algorithm for canonicalization
        under monoterm symmetries.

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> m0, m1, m2 = tensor_indices('m0,m1,m2', Lorentz)
        >>> A = tensorhead('A', [Lorentz]*2, [[2]])
        >>> t = A(m0,-m1)*A(m1,-m0)
        >>> t.canon_bp()
        -A(L_0, L_1)*A(-L_0, -L_1)
        >>> t = A(m0,-m1)*A(m1,-m2)*A(m2,-m0)
        >>> t.canon_bp()
        0
        """
        if self._is_canon_bp:
            return self
        if not self.components:
            return self
        t = self.sorted_components()
        g, dummies, msym, v = t._tids.canon_args()
        can = canonicalize(g, dummies, msym, *v)
        if can == 0:
            return S.Zero
        return t.perm2tensor(can, True)

    def _contract(self, g, antisym, contract_all=False):
        """
        helper method for ``contract_metric`` and ``contract_delta``

        ``g`` metric to be contracted

        ``antisym``:
        False  symmetric metric
        True   antisymmetric metric
        None   delta
        """
        if not self.components:
            return self
        free_indices = [x[0] for x in self.free]
        a = self.split()
        typ = g.index_types[0]
        for i, tg in enumerate(a):
            if tg.components[0] == g:
                tg_free = [x[0] for x in tg.free]
                if len(tg_free) == 0:
                    t = _contract_g_with_itself(a, i, tg, tg_free, g, antisym)
                    if contract_all == True and g in t.components:
                        return t._contract(g, antisym, True)
                    return t

                if all(indx in free_indices for indx in tg_free):
                    continue
                else:
                    break
        else:
            # all metric tensors have only free indices, there is no contraction
            return self

        # tg has one or two indices contracted with other tensors
        # i position of tg in a
        tg_free = tg.free
        if antisym:
            # order by slot position
            tg_free = sorted(tg_free, key=lambda x: x[1])

        if tg_free[0][0] in free_indices or tg_free[1][0] in free_indices:
            # tg has one free index
            res = _contract_g_with_free_index(a, free_indices, i, tg, tg_free, g, antisym)
        else:
            # tg has two indices contracted with other tensors
            res = _contract_g_without_free_index(a, free_indices, i, tg, tg_free, g, typ, antisym)
        if contract_all == True and g in res.components:
            return res._contract(g, antisym, True)
        return res

    def contract_delta(self, delta):
        t = self._contract(delta, None, True)
        return t

    def contract_metric(self, g, contract_all=False):
        """
        Raise or lower indices with the metric ``g``

        ``g``  metric

        ``contract_all`` if True, eliminate all ``g`` which are contracted

        Notes
        =====

        see the ``TensorIndexType`` docstring for the contraction conventions

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> m0, m1, m2 = tensor_indices('m0,m1,m2', Lorentz)
        >>> g = Lorentz.metric
        >>> p, q = tensorhead('p,q', [Lorentz], [[1]])
        >>> t = p(m0)*q(m1)*g(-m0, -m1)
        >>> t.canon_bp()
        metric(L_0, L_1)*p(-L_0)*q(-L_1)
        >>> t.contract_metric(g).canon_bp()
        p(L_0)*q(-L_0)
        """
        return self._contract(g, g.index_types[0].metric_antisym, contract_all)

    def substitute_indices(self, *index_tuples):
        """
        Return a tensor with free indices substituted according to ``index_tuples``

        ``index_types`` list of tuples ``(old_index, new_index)``

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> i, j, k, l = tensor_indices('i,j,k,l', Lorentz)
        >>> A, B = tensorhead('A,B', [Lorentz]*2, [[1]*2])
        >>> t = A(i, k)*B(-k, -j); t
        A(i, L_0)*B(-L_0, -j)
        >>> t.substitute_indices((i,j), (j, k))
        A(j, L_0)*B(-L_0, -k)
        """
        free = self.free
        free1 = []
        for j, ipos, cpos in free:
            for i, v in index_tuples:
                if i._name == j._name and i._tensortype == j._tensortype:
                    if i._is_up == j._is_up:
                        free1.append((v, ipos, cpos))
                    else:
                        free1.append((-v, ipos, cpos))
                    break
            else:
                free1.append((j, ipos, cpos))

        return TensMul.from_data(self._coeff, self.components, free1, self.dum, self.data)

    def fun_eval(self, *index_tuples):
        """
        Return a tensor with free indices substituted according to ``index_tuples``

        ``index_types`` list of tuples ``(old_index, new_index)``

        Examples
        ========

        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
        >>> i, j, k, l = tensor_indices('i,j,k,l', Lorentz)
        >>> A, B = tensorhead('A,B', [Lorentz]*2, [[1]*2])
        >>> t = A(i, k)*B(-k, -j); t
        A(i, L_0)*B(-L_0, -j)
        >>> t.fun_eval((i, k),(-j, l))
        A(k, L_0)*B(-L_0, l)
        """
        free = self.free
        free1 = []
        for j, ipos, cpos in free:
            # search j in index_tuples
            for i, v in index_tuples:
                if i == j:
                    free1.append((v, ipos, cpos))
                    break
            else:
                free1.append((j, ipos, cpos))
        return TensMul.from_data(self._coeff, self.components, free1, self.dum)

    def __call__(self, *indices):
        """Returns tensor with ordered free indices replaced by ``indices``

        Examples
        ========

        >>> from sympy import Symbol
        >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead
        >>> D = Symbol('D')
        >>> Lorentz = TensorIndexType('Lorentz', dim=D, dummy_fmt='L')
        >>> i0,i1,i2,i3,i4 = tensor_indices('i0:5', Lorentz)
        >>> g = Lorentz.metric
        >>> p, q = tensorhead('p,q', [Lorentz], [[1]])
        >>> t = p(i0)*q(i1)*q(-i1)
        >>> t(i1)
        p(i1)*q(L_0)*q(-L_0)
        """
        free_args = self.free_args
        indices = list(indices)
        if [x._tensortype for x in indices] != [x._tensortype for x in free_args]:
            raise ValueError('incompatible types')
        if indices == free_args:
            return self
        t = self.fun_eval(*list(zip(free_args, indices)))
        return t

    def _pretty(self):
        if len(self.components) == 0:
            return str(self._coeff)
        indices = [str(ind) for ind in self.get_indices()]
        pos = 0
        a = []
        for t in self.components:
            if t._rank > 0:
                a.append('%s(%s)' % (t.name, ', '.join(indices[pos:pos + t._rank])))
            else:
                a.append('%s' % t.name)
            pos += t._rank
        res = '*'. join(a)
        if self._coeff == S.One:
            return res
        elif self._coeff == -S.One:
            return '-%s' % res
        if self._coeff.is_Atom:
            return '%s*%s' % (self._coeff, res)
        else:
            return '(%s)*%s' %(self._coeff, res)

    def applyfunc(self, func):
        """
        Return a new ``TensAdd`` object, whose data ndarray will be the elementwise
        map of the current data ndarray by function ``func``.
        """
        new_tmul = TensMul(*self.args)
        tids = new_tmul._tids
        new_tmul._tids = VTIDS(tids.components, tids.free, tids.dum, func(self.data))
        return new_tmul

    @property
    def data(self):
        if isinstance(self._tids, VTIDS):
            return self._tids.data
        return None

    @data.setter
    def data(self, data):
        # TODO: check data compatibility with properties of tensor.
        self._tids = VTIDS(self.components, self.free, self.dum, data)

    @data.deleter
    def data(self):
        self._tids = TIDS(self._tids.components, self._tids.free, self._tids.dum)

    def __iter__(self):
        if self.data is None:
            raise ValueError("No iteration on abstract tensors")
        return (self.coeff * self.data.flatten()).__iter__()


def canon_bp(p):
    """
    Butler-Portugal canonicalization
    """
    if isinstance(p, TensExpr):
        return p.canon_bp()
    return p

def tensor_mul(*a):
    """
    product of tensors
    """
    if not a:
        return TensMul.from_data(S.One, [], [], [])
    t = a[0]
    for tx in a[1:]:
        t = t*tx
    return t


def riemann_cyclic_replace(t_r):
    """
    replace Riemann tensor with an equivalent expression

    ``R(m,n,p,q) -> 2/3*R(m,n,p,q) - 1/3*R(m,q,n,p) + 1/3*R(m,p,n,q)``

    """
    free = sorted(t_r.free, key=lambda x: x[1])
    m, n, p, q = [x[0] for x in free]
    t0 = S(2)/3*t_r
    t1 = - S(1)/3*t_r.substitute_indices((m,m),(n,q),(p,n),(q,p))
    t2 = S(1)/3*t_r.substitute_indices((m,m),(n,p),(p,n),(q,q))
    t3 = t0 + t1 + t2
    return t3

def riemann_cyclic(t2):
    """
    replace each Riemann tensor with an equivalent expression
    satisfying the cyclic identity.

    This trick is discussed in the reference guide to Cadabra.

    Examples
    ========

    >>> from sympy.tensor.tensor import TensorIndexType, tensor_indices, tensorhead, riemann_cyclic
    >>> Lorentz = TensorIndexType('Lorentz', dummy_fmt='L')
    >>> i, j, k, l = tensor_indices('i,j,k,l', Lorentz)
    >>> R = tensorhead('R', [Lorentz]*4, [[2, 2]])
    >>> t = R(i,j,k,l)*(R(-i,-j,-k,-l) - 2*R(-i,-k,-j,-l))
    >>> riemann_cyclic(t)
    0
    """
    if isinstance(t2, TensMul):
        args = [t2]
    else:
        args = t2.args
    a1 = [x.split() for x in args]
    a2 = [[riemann_cyclic_replace(tx) for tx in y] for y in a1]
    a3 = [tensor_mul(*v) for v in a2]
    t3 = TensAdd(*a3)
    if not t3:
        return t3
    else:
        return canon_bp(t3)


def tensorlist_contract_metric(a, tg):
    """
    contract `tg` with a tensor in the list `a = t.split()`
    Only for symmetric metric.
    """
    ind1, ind2 = [x[0] for x in tg.free]
    mind1 = -ind1
    mind2 = -ind2
    for i in range(len(a)):
        t1 = a[i]
        for j in range(len(t1.free)):
            indx, ipos, _ = t1.free[j]
            if indx == mind1 or indx == mind2:
                ind3 = ind2 if indx == mind1 else ind1
                free1 = list(t1.free[:])
                free1[j] = (ind3, ipos, 0)
                t2 = TensMul.from_data(t1._coeff, t1.components, free1, t1.dum)
                a[i] = t2
                return a
    a.append(tg)
    return a

def _contract_g_with_itself(a, i, tg, tg_free, g, antisym):
    """
    helper function for _contract
    """
    typ = g.index_types[0]
    a1 = a[:i] + a[i + 1:]
    t11 = tensor_mul(*a1)
    if typ._dim is None:
        raise ValueError('dimension not assigned')
    coeff = typ._dim*a[i]._coeff
    if antisym and tg.dum[0][0] == 0:
        # g(i, -i) = -D
        coeff = -coeff
    t = tensor_mul(*a1)*coeff
    return t


def _contract_g_with_free_index(a, free_indices, i, tg, tg_free, g, antisym):
    """
    helper function for _contract
    """
    if tg_free[0][0] in free_indices:
        ind_free = tg_free[0][0]
        ind, ipos1, _ = tg_free[1]
    else:
        ind_free = tg_free[1][0]
        ind, ipos1, _ = tg_free[0]

    ind1 = -ind
    # search ind1 in the other component tensors
    for j, tx in enumerate(a):
        if ind1 in [x[0] for x in tx.free]:
            break
    # replace ind1 with ind_free
    free1 = []
    for indx, iposx, _ in tx.free:
        if indx == ind1:
            free1.append((ind_free, iposx, 0))
        else:
            free1.append((indx, iposx, 0))
    coeff = tx._coeff
    if antisym:
        if ind._is_up and ind == tg_free[0][0] or \
        (not ind._is_up) and ind == tg_free[1][0]:
            # g(i1, i0)*psi(-i1) = -psi(i0)
            # g(-i0, -i1)*psi(i1) = -psi(-i0)
            coeff = -coeff
    t1 = TensMul.from_data(coeff, tx.components, free1, tx.dum)
    a[j] = t1
    a = a[:i] + a[i + 1:]
    coeff = tg._coeff
    res = tensor_mul(*a)
    return coeff*res


def _contract_g_without_free_index(a, free_indices, i, tg, tg_free, g, typ, antisym):
    """
    helper function for _contract
    """
    coeff = S.One
    ind1 = tg_free[0][0]
    ind2 = tg_free[1][0]
    ind1m = -ind1
    ind2m = -ind2
    for k, ty in enumerate(a):
        if ind2m in [x[0] for x in ty.free]:
            break
    # ty has the index ind2m
    ty_free = ty.free[:]
    if ty.components == [g]:
        ty_indices = [x[0] for  x in ty_free]
        if all(x in [ind1m, ind2m] for x in ty_indices):
            # the two `g` are completely contracted
            # i < k always
            a = a[:i] + a[i+1:k] + a[k+1:]
            coeff = coeff*typ._dim*tg._coeff*ty._coeff
            if antisym:
                ty_free = sorted(ty_free, key=lambda x: x[1])
                if ind1._is_up == ind2._is_up:
                    # g(i,j)*g(-i,-j) = g(-i,-j)*g(i,j) = dim
                    # g(i,j)*g(-j,-i) = g(-i,-j)*g(j,i) = -dim
                    if ind1m == ty_free[1][0]:
                        coeff = -coeff
                else:
                    # g(-i,j)*g(i,-j) = g(i,-j)^g(-i,j) = -dim
                    # g(-i,j)*g(-j,i) = g(i,-j)*g(j,i) = dim
                    if ind1m == ty_free[0][0]:
                        coeff = -coeff

            if a:
                res = tensor_mul(*a)
                res = coeff*res
            else:
                res = TensMul.from_data(coeff, [], [], [], is_canon_bp=True)
            return res

    free2 = []
    ty_freeindices = [x[0] for x in ty_free]
    if ind1m in ty_freeindices:
        # tg has both indices contracted with ty
        free2 = [(indx, iposx, cposx) for indx, iposx, cposx in ty.free if indx != ind1m and indx != ind2m]
        dum2 = list(ty.dum[:])
        for indx, iposx, _ in ty_free:
            if indx == ind1m:
                iposx1 = iposx
            if indx == ind2m:
                iposx2 = iposx
        if antisym:
            if ind1._is_up == ind2._is_up:
                if iposx1 < iposx2:
                    coeff = -coeff
                    dum2.append((iposx1, iposx2, 0, 0))
                else:
                    dum2.append((iposx2, iposx1, 0, 0))
            else:
                if iposx1 > iposx2:
                    coeff = -coeff
                    dum2.append((iposx2, iposx1, 0, 0))
                else:
                    dum2.append((iposx1, iposx2, 0, 0))
        else:
            dum2.append((iposx1, iposx2, 0, 0))
    else:
        # replace ind2m with ind1 in the free indices of ty

        free2 = []
        if not antisym:
            for indx, iposx, _ in ty_free:
                if indx == ind2m:
                    free2.append((ind1, iposx, 0))
                else:
                    free2.append((indx, iposx, 0))
        else:
            for indx, iposx, _ in ty_free:
                if indx == ind2m:
                    free2.append((ind1, iposx, 0))
                    if indx._is_up:
                        coeff = -coeff
                else:
                    free2.append((indx, iposx, 0))
        dum2 = ty.dum

    t2 = TensMul.from_data(ty._coeff, ty.components, free2, dum2)
    a[k] = t2
    a = a[:i] + a[i + 1:]
    coeff = coeff*tg._coeff
    res = tensor_mul(*a)
    return coeff*res
