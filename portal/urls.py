from django.urls import path

from .views import auth, judge, manage

urlpatterns = [
    path("", auth.home, name="home"),
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),
    path("invite/<str:token>/", auth.accept_invite, name="accept_invite"),
    path("password/forgot/", auth.forgot_password, name="forgot_password"),
    path("password/reset/<str:token>/", auth.reset_password, name="reset_password"),
    path("account/", auth.account, name="account"),
    path(
        "passkey/register/options/", auth.passkey_register_options, name="passkey_register_options"
    ),
    path("passkey/register/verify/", auth.passkey_register_verify, name="passkey_register_verify"),
    path("passkey/login/options/", auth.passkey_login_options, name="passkey_login_options"),
    path("passkey/login/verify/", auth.passkey_login_verify, name="passkey_login_verify"),
    path("language/", auth.set_language, name="set_language"),
    # Judges
    path("judge/", judge.dashboard, name="judge_dashboard"),
    path("judge/statement/", judge.onboarding, name="judge_onboarding"),
    path("judge/rubric/", judge.rubric, name="judge_rubric"),
    path("judge/essay/<str:code>/", judge.sheet, name="judge_sheet"),
    path("judge/essay/<str:code>/page/<int:number>/", judge.page, name="judge_page"),
    path("judge/essay/<str:code>/autosave/", judge.autosave, name="judge_autosave"),
    path("judge/essay/<str:code>/recuse/", judge.recuse, name="judge_recuse"),
    # Committee
    path("manage/", manage.dashboard, name="manage_dashboard"),
    path("manage/essays/", manage.essays, name="manage_essays"),
    path("manage/essays/upload/", manage.upload, name="manage_upload"),
    path("manage/essays/upload/file/", manage.upload_file, name="manage_upload_file"),
    path("manage/essays/authors/", manage.import_metadata, name="manage_import_metadata"),
    path("manage/essays/<int:pk>/", manage.essay_detail, name="manage_essay"),
    path("manage/essays/<int:pk>/original/", manage.original_file, name="manage_original"),
    path("manage/essays/<int:pk>/page/<int:number>/", manage.work_page, name="manage_page"),
    path("manage/essays/<int:pk>/preview/", manage.preview, name="manage_preview"),
    path(
        "manage/essays/<int:pk>/preview/<int:number>/",
        manage.released_page,
        name="manage_released_page",
    ),
    path("manage/essays/<int:pk>/finalist/", manage.finalist, name="manage_finalist"),
    path("manage/review/", manage.review_queue, name="manage_review_queue"),
    path("manage/review/<int:pk>/", manage.review, name="manage_review"),
    path("manage/people/", manage.users, name="manage_users"),
    path("manage/people/<int:pk>/", manage.user_detail, name="manage_user"),
    path("manage/assignments/", manage.assignments, name="manage_assignments"),
    path("manage/divergence/", manage.divergence, name="manage_divergence"),
    path("manage/referrals/", manage.referrals, name="manage_referrals"),
    path("manage/sheets/<int:pk>/", manage.sheet_view, name="manage_sheet"),
    path("manage/results/", manage.results, name="manage_results"),
    path("manage/export/<str:kind>/", manage.export, name="manage_export"),
    path("manage/prompts/", manage.prompts, name="manage_prompts"),
    path("manage/prompts/<int:pk>/", manage.prompts, name="manage_prompt"),
    path("manage/settings/", manage.contest_settings, name="manage_settings"),
    path("manage/logs/", manage.logs, name="manage_logs"),
]
