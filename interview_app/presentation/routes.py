from collections.abc import Callable

from flask import Flask, current_app, flash, jsonify, redirect, render_template, request, url_for

from interview_app.handlers import catalog_handler, generation_handler, home_handler, review_handler
from interview_app.handlers.deps import HandlerDepsBundle


DepsProvider = Callable[[], HandlerDepsBundle]


def register_routes(app: Flask, deps_provider: DepsProvider) -> None:
    def index():
        return home_handler.index_page(
            deps=deps_provider().home,
            render_template_fn=render_template,
        )

    def generate():
        return generation_handler.generate_page(
            deps=deps_provider().generation,
            request_obj=request,
            flash_fn=flash,
            redirect_fn=redirect,
            url_for_fn=url_for,
            render_template_fn=render_template,
        )

    def generate_start():
        return generation_handler.generate_start(
            deps=deps_provider().generation,
            request_obj=request,
            jsonify_fn=jsonify,
            app_obj=current_app._get_current_object(),
        )

    def generate_progress(job_id: str):
        return generation_handler.generate_progress(
            job_id=job_id,
            jsonify_fn=jsonify,
        )

    def generate_scope_preview():
        return generation_handler.generate_scope_preview(
            deps=deps_provider().generation,
            request_obj=request,
            jsonify_fn=jsonify,
        )

    def review():
        return review_handler.review_page(
            deps=deps_provider().review,
            request_obj=request,
            render_template_fn=render_template,
        )

    def review_submit(question_id: int):
        return review_handler.review_submit_action(
            deps=deps_provider().review,
            question_id=question_id,
            request_obj=request,
            flash_fn=flash,
            redirect_fn=redirect,
            url_for_fn=url_for,
        )

    def review_skip(question_id: int):
        return review_handler.review_skip_action(
            deps=deps_provider().review,
            question_id=question_id,
            request_obj=request,
        )

    def review_answer(question_id: int):
        return review_handler.review_answer_action(
            deps=deps_provider().review,
            question_id=question_id,
            request_obj=request,
            flash_fn=flash,
            redirect_fn=redirect,
            url_for_fn=url_for,
        )

    def review_feedback(question_id: int):
        return review_handler.review_feedback_action(
            deps=deps_provider().review,
            question_id=question_id,
            request_obj=request,
            flash_fn=flash,
            redirect_fn=redirect,
            url_for_fn=url_for,
        )

    def review_transcribe():
        return review_handler.review_transcribe_action(
            deps=deps_provider().review,
            request_obj=request,
            jsonify_fn=jsonify,
        )

    def questions():
        return catalog_handler.questions_page(
            deps=deps_provider().catalog,
            render_template_fn=render_template,
        )

    def topics():
        return catalog_handler.topics_page(
            deps=deps_provider().catalog,
            request_obj=request,
            render_template_fn=render_template,
        )

    def question_update(question_id: int):
        return catalog_handler.question_update_action(
            deps=deps_provider().catalog,
            question_id=question_id,
            request_obj=request,
            flash_fn=flash,
            redirect_fn=redirect,
            url_for_fn=url_for,
        )

    def question_delete(question_id: int):
        return catalog_handler.question_delete_action(
            deps=deps_provider().catalog,
            question_id=question_id,
            request_obj=request,
            flash_fn=flash,
            redirect_fn=redirect,
            url_for_fn=url_for,
        )

    def topic_rename():
        return catalog_handler.topic_rename_action(
            deps=deps_provider().catalog,
            request_obj=request,
            flash_fn=flash,
            redirect_fn=redirect,
            url_for_fn=url_for,
        )

    def topic_delete():
        return catalog_handler.topic_delete_action(
            deps=deps_provider().catalog,
            request_obj=request,
            flash_fn=flash,
            redirect_fn=redirect,
            url_for_fn=url_for,
        )

    def subtopic_rename():
        return catalog_handler.subtopic_rename_action(
            deps=deps_provider().catalog,
            request_obj=request,
            flash_fn=flash,
            redirect_fn=redirect,
            url_for_fn=url_for,
        )

    def subtopic_delete():
        return catalog_handler.subtopic_delete_action(
            deps=deps_provider().catalog,
            request_obj=request,
            flash_fn=flash,
            redirect_fn=redirect,
            url_for_fn=url_for,
        )

    app.add_url_rule("/", endpoint="index", view_func=index, methods=["GET"])
    app.add_url_rule("/generate", endpoint="generate", view_func=generate, methods=["GET", "POST"])
    app.add_url_rule("/generate/start", endpoint="generate_start", view_func=generate_start, methods=["POST"])
    app.add_url_rule(
        "/generate/progress/<string:job_id>",
        endpoint="generate_progress",
        view_func=generate_progress,
        methods=["GET"],
    )
    app.add_url_rule(
        "/generate/scope-preview",
        endpoint="generate_scope_preview",
        view_func=generate_scope_preview,
        methods=["GET"],
    )
    app.add_url_rule("/review", endpoint="review", view_func=review, methods=["GET"])
    app.add_url_rule(
        "/review/<int:question_id>",
        endpoint="review_submit",
        view_func=review_submit,
        methods=["POST"],
    )
    app.add_url_rule(
        "/review/<int:question_id>/skip",
        endpoint="review_skip",
        view_func=review_skip,
        methods=["POST"],
    )
    app.add_url_rule(
        "/review/<int:question_id>/answer",
        endpoint="review_answer",
        view_func=review_answer,
        methods=["POST"],
    )
    app.add_url_rule(
        "/review/<int:question_id>/feedback",
        endpoint="review_feedback",
        view_func=review_feedback,
        methods=["POST"],
    )
    app.add_url_rule(
        "/review/transcribe",
        endpoint="review_transcribe",
        view_func=review_transcribe,
        methods=["POST"],
    )
    app.add_url_rule("/questions", endpoint="questions", view_func=questions, methods=["GET"])
    app.add_url_rule("/topics", endpoint="topics", view_func=topics, methods=["GET"])
    app.add_url_rule(
        "/questions/<int:question_id>/edit",
        endpoint="question_update",
        view_func=question_update,
        methods=["POST"],
    )
    app.add_url_rule(
        "/questions/<int:question_id>/delete",
        endpoint="question_delete",
        view_func=question_delete,
        methods=["POST"],
    )
    app.add_url_rule(
        "/topics/edit",
        endpoint="topic_rename",
        view_func=topic_rename,
        methods=["POST"],
    )
    app.add_url_rule(
        "/topics/delete",
        endpoint="topic_delete",
        view_func=topic_delete,
        methods=["POST"],
    )
    app.add_url_rule(
        "/subtopics/edit",
        endpoint="subtopic_rename",
        view_func=subtopic_rename,
        methods=["POST"],
    )
    app.add_url_rule(
        "/subtopics/delete",
        endpoint="subtopic_delete",
        view_func=subtopic_delete,
        methods=["POST"],
    )
