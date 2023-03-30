r"""
LpaSeed

This class implements seed and their mutations for Lam and Pylyavskyy's Laurent 
phenomenon algebras (LP algebras). It is designed to have similar functionality
to the previous SageMath cluster seed packages.

Fixing a unique factorization domain `A`, a pair `(\mathbf{x}, \mathbf{f})` is 
said to be an *LP seed* if `\mathbf{x}=\{x_1, \dots, x_n\}` is a transcendence
basis for the field of rational functions in `n` independent variables over
`\text{Frac}(A)`, and `\mathbf{f} = \{f_1, \dots, f_n\}` is a collection of 
irreducible polynomials over `A` encoding the exchange relations.

One can view LP seeds and their corresponding LP algebras as a vast
generalisation of Fomin and Zelevinsky's cluster algebras. This module provides
basic functionality for investigating their properties.

AUTHORS:

- Oliver Daisey (2023-03-20): initial version

"""

# ****************************************************************************
#       Copyright (C) 2022 Oliver Daisey <oliver.j.daisey at durham.ac.uk>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#                  https://www.gnu.org/licenses/
# ****************************************************************************

import time
from copy import copy
import random
from sage.arith.all import factor, gcd
from sage.categories.unique_factorization_domains import \
    UniqueFactorizationDomains
from sage.graphs.graph import Graph
from sage.rings.fraction_field import FractionField
from sage.rings.infinity import infinity
from sage.rings.integer_ring import ZZ, IntegerRing_class
from sage.rings.polynomial.polynomial_ring_constructor import PolynomialRing
from sage.rings.rational_field import QQ, RationalField
from sage.structure.sage_object import SageObject
from sage.symbolic.ring import SR


class LpaSeed(SageObject):

    def __init__(self, data, coefficients=(),
                 base_ring=ZZ):
        r"""
        Initialises a Laurent phenomenon algebra seed.

        INPUT:

        - ``data`` -- Can be one of the following:

            * ``dict`` - dictionary of initial variable names to their 
              corresponding exchange polynomials. The exchange polynomials must 
              be irreducible, not depend on the key, and not be divisible by any
              variable. The correctness of the input data is checked 
              automatically.
            * ``LpaSeed`` object.

        - ``coefficients`` -- tuple of symbolic variables (default: ``()``); the 
          labels of, if any, the coefficients of the exchange polynomials. If no 
          coefficients are provided, the module attempts to detect them from the
          input data.

        - ``base_ring`` -- Unique factorisation domain (default: ``ZZ``); 
          the ring which we take the exchange polynomials over. Currently 
          supports ``ZZ`` or ``QQ``.

        OUTPUT: an ``LpaSeed`` object

        EXAMPLES:

        This example initialises a linear Laurent phenomenon algebra in two 
        variables: ::

            sage: var('x1,x2')
            (x1, x2)
            sage: S = LpaSeed({x1: 1 + x2,x2: 1 + x1})
            sage: print(S)
            A seed with cluster variables [x1, x2] and exchange polynomials [x2 + 1, x1 + 1]

        We add some coefficients to get the generic linear LP algebra in three 
        variables: ::

            sage: var('x1,x2,x3,a0,a2,a3,b0,b1,b3,c0,c1,c2')
            (x1, x2, x3, a0, a2, a3, b0, b1, b3, c0, c1, c2)
            sage: S = LpaSeed({x1: a0 + a2*x2 + a3*x3, x2: b0 + b1*x1 + b3*x3, x3: c0 + c1*x1 + c2*x2})
            sage: print(S)
            A seed with cluster variables [x1, x2, x3] and exchange polynomials [x3*a3 + x2*a2 + a0, x3*b3 + x1*b1 + b0, x2*c2 + x1*c1 + c0]

        More complicated polynomials are allowed, as long as they are
        irreducible:  ::

            sage: var('x1,x2,x3')
            (x1, x2, x3)
            sage: S = LpaSeed({x1: 1 + x2*x3^2 + 4*x3^3, x2: 2 - x1^2, x3: 4 + x1^3*x2^2 - 3*x1})
            sage: print(S)
            A seed with cluster variables [x1, x2, x3] and exchange polynomials [x2*x3^2 + 4*x3^3 + 1, -x1^2 + 2, x1^3*x2^2 - 3*x1 + 4]

        Nonirreducible polynomials will raise an exception: ::

            sage: var('x1, x2')
            (x1, x2)
            sage: S = LpaSeed({x1: 4 - x2^2, x2: 1 + x1})
            Traceback (most recent call last):
            ...
            ValueError: (LP2) fail: -x2^2 + 4 is not irreducible over Integer Ring

        Different base rings are allowed: ::

            sage: var('x1,x2')
            (x1, x2)
            sage: S = LpaSeed({x1: 1 + x2, x2: 1 + x1}, base_ring=QQ)
            sage: print(S)
            A seed with cluster variables [x1, x2] and exchange polynomials [x2 + 1, x1 + 1]

        """

        self._names = None  # the symbolic variables we use for our polynomials
        self._base_ring = None  # the coefficient ring's base ring, A
        self._coefficients = None  # coefficients we join to A to get ring
        self._ambient_field = None  # function field F in `_names` over Frac(A)
        self._polynomial_ring = None  # exchange polynomials parent ring
        self._rank = None  # transcendence degree of F over Frac(A)
        self._exchange_polys = None  # tuple of polynomials in `_names`
        self._laurent_polys = None  # tuple of laurent polynomials in `_names`
        self._cluster_vars = None  # cluster variables for this seed
        self._mutation_sequence = None  # sequence we have already mutated at

        # unpack supplied data

        # make a copy
        if isinstance(data, LpaSeed):

            self._names = data._names
            self._base_ring = data._base_ring
            self._coefficients = data._coefficients
            self._ambient_field = data._ambient_field
            self._polynomial_ring = data._polynomial_ring
            self._rank = data._rank
            self._exchange_polys = copy(data._exchange_polys)
            self._laurent_polys = copy(data._laurent_polys)
            self._cluster_vars = copy(data._cluster_vars)
            self._mutation_sequence = copy(data._mutation_sequence)

        # we assume we have dictionary of variable/poly pairs
        elif isinstance(data, dict):

            names = tuple(data.keys())  # ensure names are immutable

            # if we are not supplied any coefficients, check input data
            if coefficients == ():
                for name in names:
                    # variables present in this polynomial
                    try:
                        name_poly_vars = set(SR(data[name]).variables())
                    except:
                        raise TypeError('Values of dictionary are not polynomials')
                    # add the variables that are not already names
                    coefficients += tuple(name_poly_vars.difference(set(names)))

            coefficients = tuple(coefficients)  # coefficients are immutable
            exchange_polys = list(data.values())

            self._names = names

            # construct the ambient ring from input data

            # first we get generators for ambient ring
            variables = names + coefficients

            # now attempt to build polynomial ring from this data
            if not isinstance(base_ring, (IntegerRing_class, RationalField)):
                raise ValueError('%s is a nonsupported base ring. ZZ or QQ only.' %
                                 (base_ring))

            self._base_ring = base_ring
            try:
                self._polynomial_ring = PolynomialRing(self._base_ring,
                                                       names=variables)
            except:
                raise TypeError('Supplied variables / coefficients are not correct')

            self._ambient_field = FractionField(self._polynomial_ring)
            self._rank = len(self._names)

            # we get initial cluster variables by casting initial variables as
            # rational functions
            self._cluster_vars = [self._ambient_field(self._names[i])
                                  for i in range(0, self._rank)]

            # take what input data we were given and try to use it to
            # construct polynomials
            self._exchange_polys = []
            try:
                for i in range(self._rank):
                    self._exchange_polys.append(
                        self._polynomial_ring(exchange_polys[i]))
            except:
                raise TypeError(("The supplied exchange polynomials are not"
                                 " polynomials in the cluster variables over %s"
                                 % (base_ring)))

            self._coefficients = coefficients
            self._check_seed()

            # ensure mutation sequence / seed list initialises as empty lists
            self._mutation_sequence = []

            # begin with correct Laurent polynomials
            self._laurent_polys = self._exchange_polys.copy()
            self._compute_laurent()

        else:
            raise TypeError('Nonsupported input data. See documentation.')

    # a private method to do some mathematical checks on our seed

    def _check_seed(self):

        # we shouldn't get this error as we restrict coefficient rings in
        # constructor
        if self._base_ring not in UniqueFactorizationDomains:
            raise TypeError('%s is not a UFD.' % (self._base_ring))

        # (LP1) check polynomials do not depend on their cluster variable

        for i in range(0, self._rank):
            currPoly = self._exchange_polys[i]
            varList = currPoly.variables()
            if self._names[i] in varList:
                raise ValueError("(LP1) fail: %s depends on %s" %
                                 (self._exchange_polys[i], self._names[i]))

        # (LP2) check exchange polynomials are irreducible
        # and not divisible by any cluster variable

        for f in self._exchange_polys:
            # check irreducibility
            L = list(factor(f))
            if (len(L) > 1) or f.is_unit():
                raise ValueError("(LP2) fail: %s is not irreducible over %s"
                                 % (f, self._base_ring))

            # check not divisible by any variable
            for var in self._names:
                (q, r) = f.quo_rem(self._polynomial_ring(self._names[i]))
                if r == 0:
                    raise ValueError("(LP2) fail: %s divides %s" % (var, f))

    # a private method to compute the exchange Laurent polynomials of `self`

    def _compute_laurent(self):

        # work with copies as we perform substitutions
        exchange_polys = self._exchange_polys.copy()
        laurent_polys = self._exchange_polys.copy()

        for i in range(0, self._rank):

            # this is the exchange polynomial we are
            # finding laurent polynomial for
            current_poly = exchange_polys[i]

            # we build the laurent polynomial from scratch by iterating
            # through the other variables, dividing by appropriate variable
            # if necessary
            for j in range(0, self._rank):
                if i != j:

                    # this is the polynomial we want to check
                    # divisibility for
                    sub_poly = current_poly.subs(
                        **{str(self._names[j]): exchange_polys[j]})

                    # calculate maximal power of exchange_polys[j] that
                    # divides sub_poly
                    counter = 0
                    while True:
                        (q, r) = sub_poly.quo_rem(
                            exchange_polys[j] ** (counter+1))
                        if r != 0:
                            break
                        counter = counter+1

                    # divide exchange polynomial by this maximal power
                    laurent_polys[i] = laurent_polys[i]/(
                        self._polynomial_ring(self._names[j]) ** counter)

        # after performing all substitutions, set internal laurent polynomials
        self._laurent_polys = laurent_polys

    # mutates self at ith variable

    def mutate(self, i, inplace=True):
        r"""
        Mutates this seed at the ``i`` th index.

        INPUT:

        - ``i`` -- integer or iterable of integers; the index/indices to mutate 
          ``self`` at, where we index from 0.

        - ``inplace`` -- boolean (default: ``True``); whether to mutate the
          current instance of the seed, or return a new ``LpaSeed`` object.

        EXAMPLES:

        We mutate a rank-two Laurent phenomenon algebra at the first index. ::

            sage: var('x1,x2,a0,a2,b0,b1')
            (x1, x2, a0, a2, b0, b1)
            sage: S = LpaSeed({x1: a0 + a2*x2, x2: b0 + b1*x1})
            sage: print(S)
            A seed with cluster variables [x1, x2] and exchange polynomials [x2*a2 + a0, x1*b1 + b0]
            sage: S.mutate(0); print(S)
            A seed with cluster variables [(x2*a2 + a0)/x1, x2] and exchange polynomials [x2*a2 + a0, a0*b1 + x1*b0]

        Mutating at the same index is an involution: ::

            sage: var('x1,x2,x3')
            (x1, x2, x3)
            sage: S = LpaSeed({x1: 1 + x2*x3, x2: 1 + x1^2 + x3^2, x3: 1 + x1 + x2})
            sage: T = S.mutate([2,2], inplace=False)
            sage: print(T == S)
            True
        """

        # input preprocessing

        if not isinstance(inplace, bool):
            raise TypeError('The parameter inplace must be a boolean; got %s'
                            % (type(inplace)))

        if not inplace:
            self = LpaSeed(self)

        # is our input data iterable?
        if hasattr(i, '__iter__'):
            for index in i:
                if index not in range(0, self._rank):
                    raise IndexError('Iterable %s contains a nonvalid index %s'
                                     % (i, index))
                self.mutate(index)
            if not inplace:
                return self
            else:
                return

        elif i not in range(0, self._rank):
            raise IndexError('Did not pass in a valid integer index')

        # Mutate cluster variables:

        xi = self._names[i]  # the variable we are mutating at

        # get the new cluster variable by applying exchange relation
        # need to cast names as polynomials for subs method
        d = {str(self._names[j]): self._cluster_vars[j] for j in range(
            self._rank)}
        exchange_laurent_poly = self._laurent_polys[i].subs(**d)
        self._cluster_vars[i] = exchange_laurent_poly / self._cluster_vars[i]

        # Mutate exchange polynomials:

        for j in range(0, self._rank):
            if (j != i and xi in self._exchange_polys[j].variables()):

                xj = self._names[j]  # the variable corresponding to this poly

                # MUTATION ALGORITHM:

                # SUBSTITUTION:
                h = self._laurent_polys[i].subs(**{str(xj): 0})
                G = self._exchange_polys[j].subs(**{str(xi): (h / xi)})
                G = self._polynomial_ring(G.numerator())

                # CANCELLATION:
                G_factors = list(G.factor())
                H = 1  # this will be G with all common factors with h removed
                for factor in G_factors:
                    if (gcd(h.numerator(), factor[0]) == 1):
                        H = H*(factor[0]) ** (factor[1])

                # NORMALISATION:
                self._exchange_polys[j] = H.numerator()

        # after completing all transformations, update the sequence of mutations
        self._mutation_sequence.append(i)

        # make sure we have up-to-date laurent polynomials
        self._compute_laurent()

        if not inplace:
            return self

    def is_mutation_equivalent(self, other_seed):
        r"""
        Returns whether this seed and ``other_seed`` are mutation equivalent.

        INPUT:

        - ``other_seed`` -- ``LpaSeed`` object; the seed we wish to compare to.

        OUTPUT:

        - ``True`` if the two seeds are mutation equivalent, and ``False``
          otherwise.

        EXAMPLES:

        A seed is mutation equivalent to any of its mutations: ::

            sage: var('x1,x2,x3')
            (x1, x2, x3)
            sage: S = LpaSeed({x1: 1 + x2 + x3, x2: 1 + x1 + x3, x3: 1 + x1 + x2})
            sage: T = S.mutate(0, inplace=False)
            sage: print(S.is_mutation_equivalent(T))
            True
        """

        if not isinstance(other_seed, LpaSeed):
            raise ValueError('%s is not a seed!' % (other_seed))

        for i in range(self._rank):
            seed_test = LpaSeed(self)
            seed_test.mutate(i)
            if seed_test == other_seed:
                return True
        return False

    def mutation_class_iter(self, depth=infinity, show_depth=False,
                            return_paths=False, algorithm='BFS'):
        r"""
        Returns an iterator for the mutation class of this seed.

        INPUT:

        - ``depth`` -- Integer (default: ``infinity``); only return seeds at
          most ``depth`` mutations away from the initial seed.

        - ``show_depth`` -- Boolean (default: ``False``); if ``True``, the 
          current depth of recursion for the chosen algorithm is shown while
          computing.

        - ``return_paths`` -- Boolean (default: ``False``); if ``True``, a
          path of mutations from ``self`` to the given seed is returned as well.

        - ``algorithm`` -- String (default: ``'BFS'``); the search algorithm to
          find new seeds. Currently supported options: ::

             * 'BFS' - breadth-first search
             * 'DFS' - depth-first search

        EXAMPLES:

        We iterate over the mutation class for a rank two seed: ::

            sage: var('x1,x2')
            (x1, x2)
            sage: S = LpaSeed({x1: 1 + x2, x2: 1 + x1})
            sage: t = S.mutation_class_iter()
            sage: for seed in t: print(seed.cluster())
            (x1, x2)
            ((x2 + 1)/x1, x2)
            (x1, (x1 + 1)/x2)
            ((x2 + 1)/x1, (x1 + x2 + 1)/(x1*x2))
            ((x1 + x2 + 1)/(x1*x2), (x1 + 1)/x2)

        Non finite-type works if we specify a fixed depth, but seeds can get big
        rather quickly: ::

            sage: var('x1,x2')
            (x1, x2)
            sage: S = LpaSeed({x1: 1 + x2 + x2^2, x2: 1 + x1 + x1^2})
            sage: t = S.mutation_class_iter(depth=15,algorithm='DFS')
            sage: for seed in t: print(seed.cluster()[0].denominator())
            1
            x1
            1
            x1*x2^2
            x1*x2^2
            x1^3*x2^4
            x1^3*x2^4
            x1^5*x2^6
            x1^5*x2^6
            x1^7*x2^8
            x1^7*x2^8
            x1^9*x2^10
            x1^9*x2^10
            x1^11*x2^12
            x1^11*x2^12
            x1^13*x2^14

        We can print computational statistics when computing large examples: ::

            sage: var('x1,x2,x3,x4,a0,a2,a3,a4,b0,b1,b3,b4,c0,c1,c2,c4,d0,d1,d2,d3')
            (x1, x2, x3, x4, a0, a2, a3, a4, b0, b1, b3, b4, c0, c1, c2, c4, d0, d1, d2, d3)
            sage: S = LpaSeed({x1: a0 + a2*x2 + a3*x3 + a4*x4, x2: b0 + b1*x1 + b3*x3 + b4*x4, x3: c0 + c1*x1 + c2*x2 + c4*x4, x4: d0 + d1*x1 + d2*x2 + d3*x3})
            sage: t = S.mutation_class_iter(show_depth=True);
            sage: for seed in t: 0  # random long time (10 seconds)
            Depth: 0     found: 1          Time: 0.00 s
            Depth: 1     found: 5          Time: 0.03 s
            Depth: 2     found: 17         Time: 0.16 s
            Depth: 3     found: 41         Time: 0.93 s
            Depth: 4     found: 65         Time: 4.41 s

        """

        # preprocess

        try:
            algorithm = str(algorithm)
        except:
            raise TypeError('Expected string for algorithm: got %s'
                            % (type(algorithm)))

        # initialise

        n = self._rank
        seeds_found = [self]
        timer = time.time()
        current_depth = 0
        seeds_to_check = [self]

        # If we are showing depth, show some statistics
        if show_depth:
            timer2 = time.time()
            dc = str(current_depth)
            dc += ' ' * (5-len(dc))
            nr = str(len(seeds_found))
            nr += ' ' * (10-len(nr))
            print("Depth: %s found: %s Time: %.2f s" % (dc, nr, timer2-timer))

        if return_paths:
            yield (self, [])
        else:
            yield self

        if algorithm == 'BFS':

            new_seeds_found = True

            while (new_seeds_found and current_depth < depth):

                current_depth += 1
                new_seeds = []  # reset new seed list

                for seed in seeds_to_check:

                    # we do not need to check the index we last mutated at
                    if seed._mutation_sequence == []:
                        last_index = None
                    else:
                        last_index = seed._mutation_sequence[-1]

                    for i in [index for index in range(n) if index != last_index]:
                        seed2 = seed.mutate(i, inplace=False)
                        if seed2 not in seeds_found:
                            new_seeds += [seed2]
                            seeds_found += [seed2]
                            if return_paths:
                                yield (seed2, seed2.mutation_sequence())
                            else:
                                yield seed2

                new_seeds_found = (len(new_seeds) != 0)
                seeds_to_check = new_seeds

                if new_seeds_found and show_depth:
                    timer2 = time.time()
                    dc = str(current_depth)
                    dc += ' ' * (5-len(dc))
                    nr = str(len(seeds_found))
                    nr += ' ' * (10-len(nr))
                    print("Depth: %s found: %s Time: %.2f s"
                          % (dc, nr, timer2-timer))

        elif algorithm == 'DFS':

            new_seeds_found = False
            while seeds_to_check != []:

                current_depth += 1
                seed = seeds_to_check.pop()

                # are we still within depth constraint?

                if current_depth < depth:

                    # we do not need to check the index we last mutated at
                    if seed._mutation_sequence == []:
                        last_index = None
                    else:
                        last_index = seed._mutation_sequence[-1]

                    for i in [index for index in range(n) if index != last_index]:

                        seed2 = seed.mutate(i, inplace=False)

                        if seed2 not in seeds_found:

                            new_seeds_found = True
                            seeds_found.append(seed2)
                            seeds_to_check.append(seed2)

                            if return_paths:
                                yield (seed2, seed2.mutation_sequence())
                            else:
                                yield seed2

                if not new_seeds_found:

                    current_depth -= 1

                elif show_depth:
                    timer2 = time.time()
                    dc = str(current_depth)
                    dc += ' ' * (5-len(dc))
                    nr = str(len(seeds_found))
                    nr += ' ' * (10-len(nr))
                    print("Depth: %s found: %s Time: %.2f s"
                          % (dc, nr, timer2-timer))

        # if the user did not supply a valid algorithm, complain
        else:

            raise ValueError('Nonsupported search algorithm: %s' % (algorithm))

    def mutation_class(self, depth=infinity, show_depth=False,
                       return_paths=False, algorithm='BFS'):
        r"""
        Return the mutation class of ``self`` with respect to
        certain constraints.

        .. SEEALSO::

            :meth:`mutation_class_iter`

        INPUT:

        - ``depth`` -- (default: ``infinity``) integer, only seeds with
          distance at most ``depth`` from ``self`` are returned
        - ``show_depth`` -- (default: ``False``) if ``True``, the actual depth
          of the mutation is shown
        - ``return_paths`` -- (default: ``False``) if ``True``, a path of 
          mutation sequences from ``self`` to the given seed is returned as well
        - ``algorithm`` -- String (default: ``'BFS'``); the search algorithm to
          find new seeds. Currently supported options: ::

             * 'BFS' - breadth-first search
             * 'DFS' - depth-first search

        EXAMPLES:

        - for further examples see :meth:`mutation_class_iter`.

        We validate the possible sizes of mutation classes in rank two: ::

            sage: var('x1,x2,A,B,C,D,E,F');
            (x1, x2, A, B, C, D, E, F)
            sage: S = LpaSeed({x1: C, x2: C}, coefficients=[C])
            sage: print(len(S.mutation_class()))
            3
            sage: S = LpaSeed({x1: A, x2: C + D*x1}, coefficients=[A,C,D])
            sage: print(len(S.mutation_class()))
            4
            sage: S = LpaSeed({x1: A + B*x2, x2: C + D*x1}, coefficients=[A,B,C,D])
            sage: print(len(S.mutation_class()))
            5
            sage: S = LpaSeed({x1: A + B*x2 + C*x2^2, x2: D + E*x1}, coefficients=[A,B,C,D,E])
            sage: print(len(S.mutation_class()))
            6
            sage: S = LpaSeed({x1: A + B*x2 + C*x2^2 + D*x2^3, x2: E + F*x1}, coefficients=[A,B,C,D,E,F]);
            sage: print(len(S.mutation_class()))
            8

        """

        return list(S for S in self.mutation_class_iter(depth=depth,
                                                        show_depth=show_depth,
                                                        return_paths=return_paths,
                                                        algorithm=algorithm))

    def cluster_class_iter(self, depth=infinity, show_depth=False,
                           algorithm='BFS'):
        r"""
        Iterator for the cluster class of ``self`` with respect to certain
        constraints.

        .. SEEALSO::

            :meth:`mutation_class_iter`

        INPUT:

        - ``depth`` -- (default: ``infinity``) integer, only clusters with
          distance at most ``depth`` from ``self`` are returned
        - ``show_depth`` -- (default: ``False``) if ``True``, the actual depth
          of the mutation is shown
        - ``return_paths`` -- (default: ``False``) if ``True``, a path of 
          mutation sequences from ``self`` to the given seed is returned as well
        - ``algorithm`` -- String (default: ``'BFS'``); the search algorithm to
          find new seeds. Currently supported options: ::

             * 'BFS' - breadth-first search
             * 'DFS' - depth-first search

        EXAMPLES:

        We check an example in LP: ::

            sage: var('a,f,C')
            (a, f, C)
            sage: S = LpaSeed({a: f + C, f: a + C}, coefficients=[C])
            sage: t = S.cluster_class_iter()
            sage: for cluster in t: print(cluster)
            (a, f)
            ((f + C)/a, f)
            (a, (a + C)/f)
            ((f + C)/a, (a + f + C)/(a*f))
            ((a + f + C)/(a*f), (a + C)/f)

        - for further examples see :meth:`mutation_class_iter`.

        """
        mc_iter = self.mutation_class_iter(depth=depth, show_depth=show_depth,
                                           algorithm=algorithm)
        for c in mc_iter:
            yield c.cluster()

    def cluster_class(self, depth=infinity, show_depth=False,
                      algorithm='BFS'):
        r"""
        Return the cluster class of ``self`` with respect to certain
        constraints.

        .. SEEALSO::

            :meth:`mutation_class_iter`

        INPUT:

        - ``depth`` -- (default: ``infinity``) integer, only clusters with
          distance at most ``depth`` from ``self`` are returned
        - ``show_depth`` -- (default: ``False``) if ``True``, the actual depth
          of the mutation is shown
        - ``return_paths`` -- (default: ``False``) if ``True``, a path of 
          mutation sequences from ``self`` to the given seed is returned as well
        - ``algorithm`` -- String (default: ``'BFS'``); the search algorithm to
          find new seeds. Currently supported options: ::

             * 'BFS' - breadth-first search
             * 'DFS' - depth-first search

        EXAMPLES:

        - for examples see :meth:`cluster_class_iter`

        """

        return [c for c in self.cluster_class_iter(depth=depth,
                                                   show_depth=show_depth,
                                                   algorithm=algorithm)]

    def variable_class_iter(self, depth=infinity, algorithm='BFS'):
        r"""
        Returns an iterator for all cluster variables in the mutation class of 
        ``self`` in seeds at most ``depth`` away from ``self``.

        INPUT:

        - ``depth`` -- (default:``infinity``) integer, only seeds with 
          distance at most ``depth`` from ``self`` are returned.
        - ``algorithm`` -- String (default: ``BFS``); the search algorithm
          to find new seeds. Currently supported options: ::

             * 'BFS' - breadth-first search
             * 'DFS' - depth-first search

        EXAMPLES:

        We define a simple iterator for the denominators of seeds in the
        mutation class: ::

            sage: var('x1, x2, x3, a0, a2, a3, b0, b1, b3, c0, c1, c2')
            (x1, x2, x3, a0, a2, a3, b0, b1, b3, c0, c1, c2)
            sage: S = LpaSeed({x1: a0 + a2*x2 + a3*x3, x2: b0 + b1*x1 + b3*x3, x3: c0 + c1*x1 + c2*x2})
            sage: t = S.variable_class_iter()
            sage: for variable in t: print(variable.denominator())
            1
            1
            1
            x1
            x2
            x3
            x1*x2
            x1*x3
            x2*x3
            x1*x2*x3
        """
        mut_iter = self.mutation_class_iter(depth=depth, show_depth=False,
                                            algorithm=algorithm)
        var_class = set()

        for seed in mut_iter:
            for x in seed.cluster():
                if x not in var_class:
                    var_class.add(x)
                    yield x

    def variable_class(self, depth=infinity):
        r"""
        Returns all cluster variables in the mutation class of ``self``. These
        are exactly the generators for the LP algebra generated by this seed.

        INPUT:

        - ``depth`` -- (default:``infinity``) integer, only seeds with distance
          at most depth from ``self`` are returned.

        EXAMPLES:

        - for more examples see :meth:`variable_class_iter`.

        We find the generators for various LP algebras: ::

            sage: var('x1,x2,x3')
            (x1, x2, x3)
            sage: S = LpaSeed({x1: 1 + x2, x2: 1 + x1})
            sage: print(S.variable_class())
            [(x1 + x2 + 1)/(x1*x2), (x2 + 1)/x1, (x1 + 1)/x2, x2, x1]
            sage: S = LpaSeed({x1: 1 + x2 + x3, x2: 1 + x1 + x3, x3: 1 + x1 + x2})
            sage: print(S.variable_class())
            [(x1 + x2 + x3 + 1)/(x1*x2*x3), (x2 + x3 + 1)/x1, (x1 + x3 + 1)/x2, (x1 + x2 + 1)/x3, x3, x2, x1]


        """

        var_iter = self.variable_class_iter(depth=depth)
        return sorted(var_iter)

    def is_equivalent(self, other):
        r"""
        Returns whether ``self`` and ``other`` are equivalent as LP seeds. 
        Two seeds are equivalent if and only if there is a permutation of the
        cluster variables of one seed to get the cluster variables of the other
        seed, up to unit multipliers. Note we also overload equality to
        equivalence.

        INPUT:

        - ``other`` -- ``LpaSeed``; the seed which we are comparing ``self`` to.

        EXAMPLES:

        Mutating this rank two example five times yields an equivalent seed: ::

            sage: var('x1,x2')
            (x1, x2)
            sage: S = LpaSeed({x1: 1 + x2, x2: 1 + x1})
            sage: print(S==S.mutate([0,1,0,1,0], inplace=False))
            True

        """
        if not isinstance(other, LpaSeed):
            raise ValueError('%s is not a seed!' % (other))

        if self._rank != other._rank:
            return False

        n = self._rank
        L = []
        for i in range(n):
            for j in range(n):
                x = other._cluster_vars[j]
                y = self._cluster_vars[i]
                t = x/y
                if t.numerator().is_unit() and t.denominator().is_unit():
                    L.append(j)
        return len(L) == n

    def exchange_graph(self):
        r"""
        Returns the exchange graph of ``self``.

        EXAMPLES:

        We work out the exchange graph for a rank-two example: ::

            sage: var('x1, x2')
            (x1, x2)
            sage: LpaSeed({x1: 1 + x2, x2: 1 + x1}).exchange_graph()
            Graph on 5 vertices

        .. PLOT::

            var('x1, x2')
            G = LpaSeed({x1: 1 + x2, x2: 1 + x1}).exchange_graph()
            sphinx_plot(G)

        A rank three example: ::

            sage: var('x1, x2, x3')
            (x1, x2, x3)
            sage: LpaSeed({x1: 1 + x2 + x3, x2: 1 + x1 + x3, x3: 1 + x1 + x2}).exchange_graph()
            Graph on 10 vertices

        .. PLOT::

            var('x1, x2, x3')
            G = LpaSeed({x1: 1 + x2 + x3, x2: 1 + x1 + x3, x3: 1 + x1 + x2}).exchange_graph()
            sphinx_plot(G)

        """

        # initialise

        covers = []
        n = self.rank()
        stack = [self]
        known_seeds = []

        # do a depth-first search
        while stack != []:
            i = stack.pop()
            for k in range(n):
                j = i.mutate(k, inplace=False)
                # need good convenient method of representing seeds on graph
                covers.append((frozenset(i.cluster()), frozenset(j.cluster())))
                if j not in known_seeds:
                    known_seeds += [j]
                    stack.append(j)
        G = Graph(covers)
        G.relabel()
        return G

    def cluster(self):
        r"""
        Returns the cluster variables of ``self``.

        EXAMPLES:

        Get the cluster variables after performing a mutation: ::

            sage: var('x1, x2')
            (x1, x2)
            sage: S = LpaSeed({x1: 1 + x2, x2: 1 + x1})
            sage: S.mutate(0)
            sage: S.cluster()
            ((x2 + 1)/x1, x2)
        """
        return tuple(self._cluster_vars)

    def exchange_polys(self):
        r"""
        Returns the exchange polynomials of ``self``.

        EXAMPLES:

        Get the exchange polynomials after performing a mutation: ::

            sage: var('x1, x2')
            (x1, x2)
            sage: S = LpaSeed({x1: 3 + 4*x2, x2: 5 + 6*x1})
            sage: S.mutate(0)
            sage: S.exchange_polys()
            [4*x2 + 3, 5*x1 + 18]
        """

        return self._exchange_polys

    def laurent_polys(self):
        r"""
        Returns the exchange Laurent polynomials of ``self``.

        EXAMPLES:

        This seed has non-trivial exchange Laurent polynomials: ::

            sage: var('x1, x2, x3')
            (x1, x2, x3)
            sage: S = LpaSeed({x1: 1 + x2 + x3, x2: 1 + x3, x3: 1 + x2})
            sage: S.laurent_polys()
            [(x2 + x3 + 1)/(x2*x3), x3 + 1, x2 + 1]
        """

        return self._laurent_polys

    def rank(self):
        r"""
        Returns the rank of ``self``. This is the number of 
        cluster variables in ``self``.

        EXAMPLES:

        The rank is the number of cluster variables in the seed: ::

            sage: var('x1,x2,x3,x4')
            (x1, x2, x3, x4)
            sage: LpaSeed({x1: 1 + x2, x2: 1 + x1, x3: 1 + x4, x4: 1 + x1}).rank()
            4
        """

        return self._rank

    def randomly_mutate(self, depth, inplace=True):
        r"""
        Randomly mutates this seed at ``depth`` indices. Useful for working out
        if a seed produces a finite type LP algebra.

        INPUT:

        - ``depth`` -- integer, the number of random mutations to perform.

        EXAMPLES:

        We suspect this seed is infinite type, so we perform some random
        mutations: ::

            sage: var('x1,x2,x3')
            (x1, x2, x3)
            sage: S = LpaSeed({x1: 1 + x2*x3, x2: 1 + x1, x3: 1 + x2})
            sage: S.randomly_mutate(7)  # random
            sage: print(S)  # random

        """

        indices = [random.randint(0, self._rank-1) for _ in range(depth)]

        self = self.mutate(indices, inplace)

        if not inplace:
            return self

    def mutation_sequence(self):
        r"""
        Returns the list of indices we have mutated ``self`` at.

        EXAMPLES:

        We look at the mutation sequences computed by the mutation class
        iterator: ::

            sage: var('x1, x2, x3')
            (x1, x2, x3)
            sage: S = LpaSeed({x1: 1 + x2 + x3, x2: 1 + x1 + x3, x3: 1 + x1 + x2})
            sage: t = S.mutation_class_iter(algorithm='BFS')
            sage: for seed in t: print(seed.mutation_sequence())
            []
            [0]
            [1]
            [2]
            [0, 1]
            [0, 2]
            [1, 0]
            [1, 2]
            [2, 0]
            [2, 1]
            sage: t = S.mutation_class_iter(algorithm='DFS')
            sage: for seed in t: print(seed.mutation_sequence())
            []
            [0]
            [1]
            [2]
            [2, 0]
            [2, 1]
            [2, 1, 2]
            [2, 1, 2, 0]
            [2, 1, 2, 0, 2]
            [2, 1, 2, 0, 2, 0]
        """

        return LpaSeed._remove_repeat_indices(self._mutation_sequence)

    # equality is currently defined as equivalence (might change later)

    def __eq__(self, other):

        # we check if cluster variables are is_equivalent of each other,
        # up to unit multiple. Since clusters determine the seed,
        # this is sufficient
        return self.is_equivalent(other)

    def _copy_(self):
        r"""
        Returns a copy of `self`.
        """
        return LpaSeed(self)

    def _repr_(self):
        return ("A seed with cluster variables {0}"
                " and exchange polynomials {1}").format(self._cluster_vars,
                                                        self._exchange_polys)

    def __hash__(self):
        """
        Return a hash of ``self``.

        EXAMPLES:

        We check that two seeds with the same hash are equal: ::

            sage: var('x1,x2')
            (x1, x2)
            sage: S = LpaSeed({x1: 1 + x2, x2: 1 + x1})
            sage: T = LpaSeed(S)
            sage: S.mutate([0,1,0])
            sage: T.mutate([1,0])
            sage: print(hash(S) == hash(T))
            True
            sage: print(S == T)
            True

        """

        return hash(frozenset(self.cluster()))

    # private method to simplify mutation sequence given list L of indices
    # we essentially apply the involution rule until no consecutive entries
    # are the same

    @staticmethod
    def _remove_repeat_indices(L: list[int]) -> list[int]:
        G = []
        flag = False
        index = 0
        while index < len(L):
            if index == len(L) - 1 or L[index] != L[index+1]:
                G.append(L[index])
                index += 1
            else:
                flag = True
                index += 2  # skip over next element

        if flag == True:
            print(G)
            return LpaSeed._remove_repeat_indices(G)
        else:
            return G
