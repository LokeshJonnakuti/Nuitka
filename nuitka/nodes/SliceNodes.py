#     Copyright 2020, Kay Hayen, mailto:kay.hayen@gmail.com
#
#     Part of "Nuitka", an optimizing Python compiler that is compatible and
#     integrates with CPython, but also works on its own.
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#
""" Slice nodes.

Slices are important when working with lists. Tracking them can allow to
achieve more compact code, or predict results at compile time.

There will be a method "computeExpressionSlice" to aid predicting them.
"""

from nuitka.PythonVersions import python_version
from nuitka.specs import BuiltinParameterSpecs

from .ConstantRefNodes import ExpressionConstantNoneRef
from .ExpressionBases import (
    ExpressionChildrenHavingBase,
    ExpressionSpecBasedComputationMixin,
)
from .NodeBases import (
    SideEffectsFromChildrenMixin,
    StatementChildrenHavingBase,
)
from .NodeMakingHelpers import (
    convertNoneConstantToNone,
    makeStatementExpressionOnlyReplacementNode,
    makeStatementOnlyNodesFromExpressions,
)
from .shapes.BuiltinTypeShapes import tshape_slice


class StatementAssignmentSlice(StatementChildrenHavingBase):
    kind = "STATEMENT_ASSIGNMENT_SLICE"

    named_children = ("source", "expression", "lower", "upper")
    getLower = StatementChildrenHavingBase.childGetter("lower")
    getUpper = StatementChildrenHavingBase.childGetter("upper")

    def __init__(self, expression, lower, upper, source, source_ref):
        assert python_version < 300

        StatementChildrenHavingBase.__init__(
            self,
            values={
                "source": source,
                "expression": expression,
                "lower": lower,
                "upper": upper,
            },
            source_ref=source_ref,
        )

    def computeStatement(self, trace_collection):
        source = trace_collection.onExpression(self.subnode_source)

        # No assignment will occur, if the assignment source raises, so strip it
        # away.
        if source.willRaiseException(BaseException):
            result = makeStatementExpressionOnlyReplacementNode(
                expression=source, node=self
            )

            return (
                result,
                "new_raise",
                """\
Slice assignment raises exception in assigned value, removed assignment.""",
            )

        lookup_source = trace_collection.onExpression(self.subnode_expression)

        if lookup_source.willRaiseException(BaseException):
            result = makeStatementOnlyNodesFromExpressions(
                expressions=(source, lookup_source)
            )

            return (
                result,
                "new_raise",
                """\
Slice assignment raises exception in sliced value, removed assignment.""",
            )

        lower = trace_collection.onExpression(self.getLower(), allow_none=True)

        if lower is not None and lower.willRaiseException(BaseException):
            result = makeStatementOnlyNodesFromExpressions(
                expressions=(source, lookup_source, lower)
            )

            return (
                result,
                "new_raise",
                """\
Slice assignment raises exception in lower slice boundary value, removed \
assignment.""",
            )

        upper = trace_collection.onExpression(self.getUpper(), allow_none=True)

        if upper is not None and upper.willRaiseException(BaseException):
            result = makeStatementOnlyNodesFromExpressions(
                expressions=(source, lookup_source, lower, upper)
            )

            return (
                result,
                "new_raise",
                """\
Slice assignment raises exception in upper slice boundary value, removed \
assignment.""",
            )

        return lookup_source.computeExpressionSetSlice(
            set_node=self,
            lower=lower,
            upper=upper,
            value_node=source,
            trace_collection=trace_collection,
        )


class StatementDelSlice(StatementChildrenHavingBase):
    kind = "STATEMENT_DEL_SLICE"

    named_children = ("expression", "lower", "upper")
    getLower = StatementChildrenHavingBase.childGetter("lower")
    getUpper = StatementChildrenHavingBase.childGetter("upper")

    def __init__(self, expression, lower, upper, source_ref):
        StatementChildrenHavingBase.__init__(
            self,
            values={"expression": expression, "lower": lower, "upper": upper},
            source_ref=source_ref,
        )

    def computeStatement(self, trace_collection):
        lookup_source = trace_collection.onExpression(self.subnode_expression)

        if lookup_source.willRaiseException(BaseException):
            result = makeStatementExpressionOnlyReplacementNode(
                expression=lookup_source, node=self
            )

            return (
                result,
                "new_raise",
                """\
Slice del raises exception in sliced value, removed del""",
            )

        lower = trace_collection.onExpression(self.getLower(), allow_none=True)

        if lower is not None and lower.willRaiseException(BaseException):
            result = makeStatementOnlyNodesFromExpressions(
                expressions=(lookup_source, lower)
            )

            return (
                result,
                "new_raise",
                """
Slice del raises exception in lower slice boundary value, removed del""",
            )

        trace_collection.onExpression(self.getUpper(), allow_none=True)
        upper = self.getUpper()

        if upper is not None and upper.willRaiseException(BaseException):
            result = makeStatementOnlyNodesFromExpressions(
                expressions=(lookup_source, lower, upper)
            )

            return (
                result,
                "new_raise",
                """
Slice del raises exception in upper slice boundary value, removed del""",
            )

        return lookup_source.computeExpressionDelSlice(
            set_node=self, lower=lower, upper=upper, trace_collection=trace_collection
        )


class ExpressionSliceLookup(ExpressionChildrenHavingBase):
    kind = "EXPRESSION_SLICE_LOOKUP"

    named_children = ("expression", "lower", "upper")
    getLower = ExpressionChildrenHavingBase.childGetter("lower")
    getUpper = ExpressionChildrenHavingBase.childGetter("upper")

    checkers = {"upper": convertNoneConstantToNone, "lower": convertNoneConstantToNone}

    def __init__(self, expression, lower, upper, source_ref):
        assert python_version < 300

        ExpressionChildrenHavingBase.__init__(
            self,
            values={"expression": expression, "upper": upper, "lower": lower},
            source_ref=source_ref,
        )

    def computeExpression(self, trace_collection):
        lookup_source = self.subnode_expression

        return lookup_source.computeExpressionSlice(
            lookup_node=self,
            lower=self.getLower(),
            upper=self.getUpper(),
            trace_collection=trace_collection,
        )

    @staticmethod
    def isKnownToBeIterable(count):
        # TODO: Should ask SliceRegistry
        return None


def makeExpressionBuiltinSlice(start, stop, step, source_ref):
    if start is None:
        start = ExpressionConstantNoneRef(source_ref=source_ref)
    if stop is None:
        stop = ExpressionConstantNoneRef(source_ref=source_ref)

    if step is None:
        return ExpressionBuiltinSlice2(start=start, stop=stop, source_ref=source_ref)
    else:
        return ExpressionBuiltinSlice3(
            start=start, stop=stop, step=step, source_ref=source_ref
        )


class ExpressionBuiltinSliceMixin(SideEffectsFromChildrenMixin):
    builtin_spec = BuiltinParameterSpecs.builtin_slice_spec

    @staticmethod
    def getTypeShape():
        return tshape_slice

    @staticmethod
    def isKnownToBeIterable(count):
        # Virtual method provided by mixin, pylint: disable=unused-argument

        # Definitely not iterable at all
        return False

    def mayHaveSideEffects(self):
        return self.mayRaiseException(BaseException)


class ExpressionBuiltinSlice3(
    ExpressionBuiltinSliceMixin,
    ExpressionSpecBasedComputationMixin,
    ExpressionChildrenHavingBase,
):
    kind = "EXPRESSION_BUILTIN_SLICE3"

    named_children = ("start", "stop", "step")

    def __init__(self, start, stop, step, source_ref):
        ExpressionChildrenHavingBase.__init__(
            self,
            values={"start": start, "stop": stop, "step": step},
            source_ref=source_ref,
        )

    def computeExpression(self, trace_collection):
        return self.computeBuiltinSpec(
            trace_collection=trace_collection,
            given_values=(self.subnode_start, self.subnode_stop, self.subnode_step),
        )

    def mayRaiseException(self, exception_type):
        return (
            self.subnode_start.mayRaiseException(exception_type)
            or self.subnode_stop.mayRaiseException(exception_type)
            or self.subnode_step.mayRaiseException(exception_type)
        )


class ExpressionBuiltinSlice2(
    ExpressionBuiltinSliceMixin,
    ExpressionSpecBasedComputationMixin,
    ExpressionChildrenHavingBase,
):
    kind = "EXPRESSION_BUILTIN_SLICE2"

    named_children = ("start", "stop")

    def __init__(self, start, stop, source_ref):
        ExpressionChildrenHavingBase.__init__(
            self,
            values={"start": start, "stop": stop},
            source_ref=source_ref,
        )

    def computeExpression(self, trace_collection):
        return self.computeBuiltinSpec(
            trace_collection=trace_collection,
            given_values=(self.subnode_start, self.subnode_stop),
        )

    def mayRaiseException(self, exception_type):
        return self.subnode_start.mayRaiseException(
            exception_type
        ) or self.subnode_stop.mayRaiseException(exception_type)
