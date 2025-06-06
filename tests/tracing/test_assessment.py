from unittest import mock

import pytest

import mlflow
from mlflow.entities.assessment import Assessment, AssessmentError, Expectation, Feedback
from mlflow.entities.assessment_source import AssessmentSource, AssessmentSourceType
from mlflow.entities.trace_data import TraceData
from mlflow.entities.trace_info_v2 import TraceInfoV2
from mlflow.entities.trace_status import TraceStatus
from mlflow.exceptions import MlflowException


# TODO: This test mocks out the tracking client and only test if the fluent API implementation
# passes the correct arguments to the low-level client. Once the OSS backend is implemented,
# we should also test the end-to-end assessment CRUD functionality.
@pytest.fixture
def store():
    mock_store = mock.MagicMock()
    with mock.patch("mlflow.tracing.client._get_store") as mock_get_store:
        mock_get_store.return_value = mock_store
        yield mock_store


# TODO: Remove this once the OSS backend is implemented
@pytest.fixture
def tracking_uri():
    original_tracking_uri = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri("databricks")
    yield
    mlflow.set_tracking_uri(original_tracking_uri)


_HUMAN_ASSESSMENT_SOURCE = AssessmentSource(
    source_type=AssessmentSourceType.HUMAN,
    source_id="bob@example.com",
)

_LLM_ASSESSMENT_SOURCE = AssessmentSource(
    source_type=AssessmentSourceType.LLM_JUDGE,
    source_id="gpt-4o-mini",
)


def test_log_expectation(store, tracking_uri):
    mlflow.log_expectation(
        trace_id="1234",
        name="expected_answer",
        value="MLflow",
        source=_HUMAN_ASSESSMENT_SOURCE,
        metadata={"key": "value"},
    )

    assert store.create_assessment.call_count == 1
    assessment = store.create_assessment.call_args[0][0]
    assert assessment.name == "expected_answer"
    assert assessment.trace_id == "1234"
    assert assessment.span_id is None
    assert assessment.source == _HUMAN_ASSESSMENT_SOURCE
    assert assessment.create_time_ms is not None
    assert assessment.last_update_time_ms is not None
    assert assessment.expectation.value == "MLflow"
    assert assessment.feedback is None
    assert assessment.rationale is None
    assert assessment.metadata == {"key": "value"}


def test_log_expectation_invalid_parameters(tracking_uri):
    with pytest.raises(MlflowException, match=r"Expectation value cannot be None."):
        mlflow.log_expectation(
            trace_id="1234",
            name="expected_answer",
            value=None,
            source=_HUMAN_ASSESSMENT_SOURCE,
        )

    with pytest.raises(MlflowException, match=r"`source` must be an instance of"):
        mlflow.log_feedback(
            trace_id="1234",
            name="faithfulness",
            value=1.0,
            source=None,
        )


def test_update_expectation(store, tracking_uri):
    mlflow.update_expectation(
        assessment_id="1234",
        trace_id="tr-1234",
        value="MLflow",
    )

    assert store.update_assessment.call_count == 1
    call_args = store.update_assessment.call_args[1]
    assert call_args["trace_id"] == "tr-1234"
    assert call_args["assessment_id"] == "1234"
    assert call_args["name"] is None
    assert call_args["expectation"] == Expectation(value="MLflow")
    assert call_args["feedback"] is None
    assert call_args["rationale"] is None
    assert call_args["metadata"] is None


def test_log_feedback(store, tracking_uri):
    mlflow.log_feedback(
        trace_id="1234",
        name="faithfulness",
        value=1.0,
        source=_LLM_ASSESSMENT_SOURCE,
        rationale="This answer is very faithful.",
        metadata={"model": "gpt-4o-mini"},
    )

    assert store.create_assessment.call_count == 1
    assessment = store.create_assessment.call_args[0][0]
    assert assessment.name == "faithfulness"
    assert assessment.trace_id == "1234"
    assert assessment.span_id is None
    assert assessment.source == _LLM_ASSESSMENT_SOURCE
    assert assessment.create_time_ms is not None
    assert assessment.last_update_time_ms is not None
    assert assessment.feedback.value == 1.0
    assert assessment.feedback.error is None
    assert assessment.expectation is None
    assert assessment.rationale == "This answer is very faithful."
    assert assessment.metadata == {"model": "gpt-4o-mini"}


def test_log_feedback_with_error(store, tracking_uri):
    mlflow.log_feedback(
        trace_id="1234",
        name="faithfulness",
        source=_LLM_ASSESSMENT_SOURCE,
        error=AssessmentError(
            error_code="RATE_LIMIT_EXCEEDED",
            error_message="Rate limit for the judge exceeded.",
        ),
    )

    assert store.create_assessment.call_count == 1
    assessment = store.create_assessment.call_args[0][0]
    assert assessment.name == "faithfulness"
    assert assessment.trace_id == "1234"
    assert assessment.span_id is None
    assert assessment.source == _LLM_ASSESSMENT_SOURCE
    assert assessment.create_time_ms is not None
    assert assessment.last_update_time_ms is not None
    assert assessment.expectation is None
    assert assessment.feedback.value is None
    assert assessment.feedback.error.error_code == "RATE_LIMIT_EXCEEDED"
    assert assessment.feedback.error.error_message == "Rate limit for the judge exceeded."
    assert assessment.rationale is None


def test_log_feedback_with_value_and_error(store, tracking_uri):
    mlflow.log_feedback(
        trace_id="1234",
        name="faithfulness",
        source=_LLM_ASSESSMENT_SOURCE,
        value=0.5,
        error=AssessmentError(
            error_code="RATE_LIMIT_EXCEEDED",
            error_message="Rate limit for the judge exceeded.",
        ),
    )

    assert store.create_assessment.call_count == 1
    assessment = store.create_assessment.call_args[0][0]
    assert assessment.name == "faithfulness"
    assert assessment.trace_id == "1234"
    assert assessment.span_id is None
    assert assessment.source == _LLM_ASSESSMENT_SOURCE
    assert assessment.create_time_ms is not None
    assert assessment.last_update_time_ms is not None
    assert assessment.expectation is None
    assert assessment.feedback.value == 0.5
    assert assessment.feedback.error.error_code == "RATE_LIMIT_EXCEEDED"
    assert assessment.feedback.error.error_message == "Rate limit for the judge exceeded."
    assert assessment.rationale is None


def test_log_feedback_invalid_parameters(tracking_uri):
    with pytest.raises(MlflowException, match=r"Either `value` or `error` must be provided."):
        mlflow.log_feedback(
            trace_id="1234",
            name="faithfulness",
            source=_LLM_ASSESSMENT_SOURCE,
        )

    with pytest.raises(MlflowException, match=r"`source` must be an instance of"):
        mlflow.log_feedback(
            trace_id="1234",
            name="faithfulness",
            value=1.0,
            source=None,
        )


def test_update_feedback(store, tracking_uri):
    mlflow.update_feedback(
        assessment_id="1234",
        trace_id="tr-1234",
        value=1.0,
        rationale="This answer is very faithful.",
        metadata={"model": "gpt-4o-mini"},
    )

    assert store.update_assessment.call_count == 1
    call_args = store.update_assessment.call_args[1]
    assert call_args["trace_id"] == "tr-1234"
    assert call_args["assessment_id"] == "1234"
    assert call_args["name"] is None
    assert call_args["expectation"] is None
    assert call_args["feedback"] == Feedback(value=1.0)
    assert call_args["rationale"] == "This answer is very faithful."
    assert call_args["metadata"] == {"model": "gpt-4o-mini"}


def test_delete_expectation(store, tracking_uri):
    mlflow.delete_expectation(trace_id="tr-1234", assessment_id="1234")

    assert store.delete_assessment.call_count == 1
    call_args = store.delete_assessment.call_args[1]
    assert call_args["assessment_id"] == "1234"
    assert call_args["trace_id"] == "tr-1234"


def test_delete_feedback(store, tracking_uri):
    mlflow.delete_feedback(trace_id="tr-5678", assessment_id="5678")

    assert store.delete_assessment.call_count == 1
    call_args = store.delete_assessment.call_args[1]
    assert call_args["assessment_id"] == "5678"
    assert call_args["trace_id"] == "tr-5678"


def test_assessment_apis_only_available_in_databricks():
    with pytest.raises(MlflowException, match=r"This API is currently only available"):
        mlflow.log_expectation(
            trace_id="1234", name="expected_answer", value="MLflow", source=_HUMAN_ASSESSMENT_SOURCE
        )

    with pytest.raises(MlflowException, match=r"This API is currently only available"):
        mlflow.log_feedback(
            trace_id="1234", name="faithfulness", value=1.0, source=_LLM_ASSESSMENT_SOURCE
        )

    with pytest.raises(MlflowException, match=r"This API is currently only available"):
        mlflow.update_expectation(trace_id="1234", assessment_id="1234", value=1.0)

    with pytest.raises(MlflowException, match=r"This API is currently only available"):
        mlflow.update_feedback(trace_id="1234", assessment_id="1234", value=1.0)

    with pytest.raises(MlflowException, match=r"This API is currently only available"):
        mlflow.delete_expectation(trace_id="1234", assessment_id="1234")

    with pytest.raises(MlflowException, match=r"This API is currently only available"):
        mlflow.delete_feedback(trace_id="1234", assessment_id="1234")


def test_search_traces_with_assessments(store, tracking_uri):
    # Create a trace info with an assessment
    assessment = Assessment(
        trace_id="test",
        name="test",
        source=AssessmentSource(source_id="test", source_type=AssessmentSourceType.HUMAN),
        create_time_ms=0,
        last_update_time_ms=0,
        feedback=Feedback("test"),
    )

    trace_info = TraceInfoV2(
        request_id="test",
        experiment_id="test",
        timestamp_ms=0,
        execution_time_ms=0,
        status=TraceStatus.OK,
        tags={"mlflow.artifactLocation": "test"},
        assessments=[assessment],  # Include the assessment here
    )

    # Mock the search_traces to return our trace_info
    store.search_traces.return_value = ([trace_info, trace_info], None)

    # Now when search_traces is called, it should use our trace_info with the assessment
    with mock.patch(
        "mlflow.tracing.client.TracingClient._download_trace_data", return_value=TraceData()
    ):
        res = mlflow.search_traces(
            experiment_ids=["0"],
            max_results=2,
            return_type="list",
        )

    # Verify the results
    assert len(res) == 2
    for trace in res:
        assert trace.info.assessments is not None
        assert len(trace.info.assessments) == 1
        assert trace.info.assessments[0].trace_id == "test"
        assert trace.info.assessments[0].name == "test"

    # Verify the search_traces was called
    assert store.search_traces.call_count == 1

    # We no longer expect get_trace_info to be called
    assert store.get_trace_info.call_count == 0
