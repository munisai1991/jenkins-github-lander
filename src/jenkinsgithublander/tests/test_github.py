"""Testing the github helpers work properly"""
import json
import responses
from unittest import TestCase

from jenkinsgithublander import (
    github,
    LanderError,
)
from jenkinsgithublander.github import (
    get_open_pull_requests,
    get_pull_request_comments,
    GithubInfo,
    GithubError,
    make_pull_request_info,
    merge_pull_request,
    mergeable_pull_requests,
    pull_request_build_failed,
    pull_request_kicked,
)
from jenkinsgithublander.tests.utils import load_data


class TestGithubError(TestCase):

    def test_github_error(self):
        """A GithubError can be made, stringified, and is a LanderError"""
        e = GithubError("Test error")
        self.assertEqual(str(e), "Test error")
        self.assertIsInstance(e, LanderError)


class TestGithubHelpers(TestCase):

    def add_user_orgs_response(self, user="jujugui"):
        user_orgs = load_data('github-user-orgs.json')
        responses.add(
            responses.GET,
            'https://api.github.com/users/{}/orgs'.format(user),
            body=user_orgs,
            status=200,
            content_type='application/json'
        )

    def add_open_pulls_response(self, user="juju", repo="project",
                                json_file="github-open-pulls.json"):
        resp_json = load_data(json_file)
        responses.add(
            responses.GET,
            'https://api.github.com/repos/{}/{}/pulls'.format(user, repo),
            body=resp_json,
            status=200,
            content_type='application/json'
        )

    def test_build_url_helper(self):
        """Should build a url given a path and a GithubInfo Tuple"""
        info = GithubInfo('juju', 'gui', 'jujugui', '1234')
        path = "/repos/{owner}/{project}/pulls"

        url = github._build_url(path, info)

        self.assertEqual(
            'https://api.github.com/repos/juju/gui/pulls?access_token=1234',
            url)

    def test_build_url_helper_with_auth(self):
        """Should build a url given a path and a GithubInfo Tuple"""
        info = GithubInfo('juju', 'gui', 'jujugui', '1234')
        path = "/repos/{owner}/{project}/pulls"

        url = github._build_url(path, info)

        self.assertEqual(
            'https://api.github.com/repos/juju/gui/pulls?access_token=1234',
            url)

    @responses.activate
    def test_user_is_not_in_org(self):
        self.add_user_orgs_response()

        info = GithubInfo('juju', 'gui', 'jujugui', '1234')
        in_org = github.user_is_in_org('jujugui', 'noexist', info)

        self.assertFalse(in_org)

    @responses.activate
    def test_user_is_in_org(self):
        self.add_user_orgs_response()

        info = GithubInfo('juju', 'gui', 'jujugui', '1234')
        in_org = github.user_is_in_org('jujugui', 'CanonicalJS', info)

        self.assertTrue(in_org)

    @responses.activate
    def test_open_pull_requests_error(self):
        """Verify a non-200 throws an error"""
        responses.add(
            responses.GET,
            'https://api.github.com/repos/juju/nope/pulls',
            body='{"error": "not found"}',
            status=404,
            content_type='application/json'
        )

        info = GithubInfo('juju', 'nope', 'jujugui', '1234')
        self.assertRaises(GithubError, github.get_open_pull_requests, info)

    @responses.activate
    def test_open_pull_requests(self):
        """Verify we can parse the list."""
        self.add_open_pulls_response()

        info = GithubInfo('juju', 'project', 'jujugui', None)
        open_requests = get_open_pull_requests(info)

        self.assertEqual(1, len(open_requests))
        self.assertTrue(
            open_requests[0]['_links']['comments']['href'].endswith(
                '/repos/CanonicalJS/juju-gui/issues/5/comments',
            )
        )

    @responses.activate
    def test_open_pull_requests_multipage(self):
        """Check multiple pull requests pages are fetched using Link header"""
        url = "https://api.github.com/repos/juju/project/pulls"
        page_1_prs = [{"number": 812}, {"number": 804}]
        page_2_prs = [{"number": 576}]
        responses.add(
            responses.GET,
            url,
            body=json.dumps(page_1_prs),
            status=200,
            content_type='application/json',
            match_querystring=True,
            adding_headers={
                "Link": '<{url}?p=2>; rel="next", <{url}?p=2>; '
                'rel="last"'.format(url=url)},
        )
        responses.add(
            responses.GET,
            url + "?p=2",
            body=json.dumps(page_2_prs),
            status=200,
            content_type='application/json',
            match_querystring=True,
            adding_headers={
                "Link":
                '<{url}>; rel="first", '
                '<{url}>; rel="prev"'.format(url=url)},
        )

        info = GithubInfo('juju', 'project', 'jujugui', None)
        open_requests = get_open_pull_requests(info)

        self.assertEqual(page_1_prs + page_2_prs, open_requests)

    @responses.activate
    def test_get_pull_request_comments(self):
        url = "https://api.testing/juju/project/issues/1/comments"
        json_comments = [{"body": "a comment"}]
        responses.add(
            responses.GET,
            url,
            body=json.dumps(json_comments),
            status=200,
            content_type='application/json'
        )

        info = GithubInfo('juju', 'project', 'jujugui', None)
        comments = get_pull_request_comments(url, info)

        self.assertEqual(json_comments, comments)

    @responses.activate
    def test_get_pull_request_comments_multipage(self):
        """Check multiple pages of comments are fetched using Link header"""
        url = "https://api.testing/juju/project/issues/2/comments"
        page_1_comments = [{"body": "a page 1 comment"}]
        page_2_comments = [{"body": "a page 2 comment"}]
        responses.add(
            responses.GET,
            url,
            body=json.dumps(page_1_comments),
            status=200,
            content_type='application/json',
            match_querystring=True,
            adding_headers={
                "Link":
                '<{url}?p=2>; rel="next", '
                '<{url}?p=2>; rel="last"'.format(url=url)},
        )
        responses.add(
            responses.GET,
            url + "?p=2",
            body=json.dumps(page_2_comments),
            status=200,
            content_type='application/json',
            match_querystring=True,
            adding_headers={
                "Link":
                '<{url}>; rel="first", '
                '<{url}>; rel="prev"'.format(url=url)},
        )

        info = GithubInfo('juju', 'project', 'jujugui', None)
        comments = get_pull_request_comments(url, info)

        self.assertEqual(page_1_comments + page_2_comments, comments)

    @responses.activate
    def test_no_mergeable_pull_requests(self):
        comments = load_data(
            'github-pull-request-comments.json',
            load_json=True)
        # Remove the first comment since it's the trigger one.
        comments.pop(0)

        self.add_open_pulls_response()

        responses.add(
            responses.GET,
            (
                u'https://api.github.com/repos/CanonicalJS/juju-gui/issues/5/'
                u'comments'
            ),
            body=json.dumps(comments),
            status=200,
            content_type='application/json'
        )

        info = GithubInfo('juju', 'project', 'jujugui', None)
        mergeable = mergeable_pull_requests('$$merge$$', info)

        self.assertEqual(0, len(mergeable))

    @responses.activate
    def test_not_mergeable_if_not_in_org(self):
        orgs = load_data('github-user-orgs.json', load_json=True)
        comments = load_data('github-pull-request-comments.json')

        # Remove the CanonicalJS group so that the user fails to be in the
        # org.
        orgs.pop(0)

        responses.add(
            responses.GET,
            'https://api.github.com/users/mitechie/orgs',
            body=json.dumps(orgs),
            status=200,
            content_type='application/json'
        )

        self.add_open_pulls_response()

        responses.add(
            responses.GET,
            (
                u'https://api.github.com/repos/CanonicalJS/juju-gui/issues/5/'
                u'comments'
            ),
            body=comments,
            status=200,
            content_type='application/json'
        )

        info = GithubInfo('juju', 'project', 'jujugui', None)
        mergeable = mergeable_pull_requests('$$merge$$', info)

        self.assertEqual(0, len(mergeable))

    @responses.activate
    def test_not_mergable_if_already_merging(self):
        comments = load_data(
            'github-pull-request-comments.json', load_json=True)

        # Add the currently merging comment to the list of the pull request to
        # verify it does not mark this as a mergable pull request then.
        merging_comment = load_data(
            'github-new-issue-comment.json', load_json=True)
        comments.append(merging_comment)

        self.add_user_orgs_response("mitechie")
        self.add_open_pulls_response("CanonicalJS", "juju-gui")
        responses.add(
            responses.GET,
            (
                u'https://api.github.com/repos/CanonicalJS/juju-gui/issues/5/'
                u'comments'
            ),
            body=json.dumps(comments),
            status=200,
            content_type='application/json'
        )

        info = GithubInfo('CanonicalJS', 'juju-gui', 'jujugui', None)
        mergeable = mergeable_pull_requests('$$merge$$', info)

        self.assertEqual(0, len(mergeable))

    @responses.activate
    def test_mergeable_pull_requests(self):
        comments = load_data('github-pull-request-comments.json')

        self.add_user_orgs_response("mitechie")
        self.add_open_pulls_response("CanonicalJS", "juju-gui")
        responses.add(
            responses.GET,
            (
                u'https://api.github.com/repos/CanonicalJS/juju-gui/issues/5/'
                u'comments'
            ),
            body=comments,
            status=200,
            content_type='application/json'
        )

        info = GithubInfo('CanonicalJS', 'juju-gui', 'jujugui', None)
        mergeable = mergeable_pull_requests('$$merge$$', info)

        self.assertEqual(1, len(mergeable))
        self.assertEqual(5, mergeable[0].number)

    @responses.activate
    def test_mergeable_pull_requests_skip_prs_with_no_repo(self):
        # This test is similar to test_mergeable_pull_requests but the 'repo'
        # is null, mimicing the case where the user has deleted the repo
        # referenced in the pull request.
        comments = load_data('github-pull-request-comments.json')

        self.add_user_orgs_response("mitechie")
        self.add_open_pulls_response(
            "CanonicalJS", "juju-gui",
            json_file="github-open-pulls-deleted-branch.json")
        responses.add(
            responses.GET,
            (
                u'https://api.github.com/repos/CanonicalJS/juju-gui/issues/5/'
                u'comments'
            ),
            body=comments,
            status=200,
            content_type='application/json'
        )

        info = GithubInfo('CanonicalJS', 'juju-gui', 'jujugui', None)
        mergeable = mergeable_pull_requests('$$merge$$', info)

        self.assertEqual(0, len(mergeable))

    @responses.activate
    def test_merge_pull_request(self):
        merge_response = load_data('github-merge-success.json')
        pulls = load_data('github-open-pulls.json', load_json=True)
        pull_request = pulls[0]

        responses.add(
            responses.GET,
            'https://api.github.com/repos/CanonicalJS/juju-gui/pulls/4',
            body=json.dumps(pull_request),
            status=200,
            content_type='application/json'
        )
        responses.add(
            responses.PUT,
            'https://api.github.com/repos/CanonicalJS/juju-gui/pulls/4/merge',
            body=merge_response,
            status=200,
            content_type='application/json'
        )

        info = GithubInfo('CanonicalJS', 'juju-gui', 'jujugui', None)
        result = merge_pull_request(
            4,
            'http://jenkins.com/job/gui/12',
            info
        )

        self.assertEqual(len(responses.calls), 2)
        self.assertEqual(responses.calls[0].request.method, "GET")
        self.assertEqual(responses.calls[1].request.method, "PUT")
        self.assertEqual(
            responses.calls[1].request.body,
            '{"commit_message": "Update hacking\\n\\n'
            'here are the changes requested."}')

        self.assertEqual(True, result['merged'])
        self.assertEqual("Pull Request successfully merged", result['message'])

    @responses.activate
    def test_merge_pull_request_fails(self):
        merge_response = load_data('github-merge-failed.json')
        pulls = load_data('github-open-pulls.json', load_json=True)
        pull_request = pulls[0]

        responses.add(
            responses.GET,
            'https://api.github.com/repos/CanonicalJS/juju-gui/pulls/4',
            body=json.dumps(pull_request),
            status=200,
            content_type='application/json'
        )

        responses.add(
            responses.PUT,
            'https://api.github.com/repos/CanonicalJS/juju-gui/pulls/4/merge',
            body=merge_response,
            status=405,
            content_type='application/json'
        )

        info = GithubInfo('CanonicalJS', 'juju-gui', 'jujugui', None)
        result = merge_pull_request(
            4,
            'http://jenkins.com/job/gui/12',
            info
        )

        self.assertEqual(False, result['merged'])
        self.assertEqual("Failure reason", result['message'])

    @responses.activate
    def test_merge_pull_request_fail_unplanned(self):
        """Still throws exception on expected request failure."""
        pulls = load_data('github-open-pulls.json', load_json=True)
        pull_request = pulls[0]

        responses.add(
            responses.GET,
            'https://api.github.com/repos/CanonicalJS/juju-gui/pulls/4',
            body=json.dumps(pull_request),
            status=200,
            content_type='application/json'
        )
        responses.add(
            responses.PUT,
            'https://api.github.com/repos/CanonicalJS/juju-gui/pulls/4/merge',
            body='Not Found',
            status=404,
            content_type='application/json'
        )

        info = GithubInfo('CanonicalJS', 'juju-gui', 'jujugui', None)

        self.assertRaises(
            GithubError,
            merge_pull_request,
            4,
            'http://jenkins.com/job/gui/12',
            info
        )

    @responses.activate
    def test_pull_request_build_failed(self):
        """Adds a comment to the pull request about the failure."""
        new_comment = load_data('github-new-issue-comment.json')
        pulls = load_data('github-open-pulls.json', load_json=True)
        pull_request = pulls[0]

        responses.add(
            responses.POST,
            (
                u'https://api.github.com/repos/CanonicalJS/juju-gui/issues/5/'
                u'comments'
            ),
            body=new_comment,
            status=201,
            content_type='application/json'
        )

        info = GithubInfo('CanonicalJS', 'juju-gui', 'jujugui', '1234')

        result = pull_request_build_failed(
            pull_request,
            'http://jenkins.com/job/gui/12',
            'Failure message',
            info
        )

        self.assertTrue('body' in result)

    @responses.activate
    def test_pull_request_kicked(self):
        new_comment = load_data('github-new-issue-comment.json')
        pulls = load_data('github-open-pulls.json', load_json=True)
        pull_request = pulls[0]

        responses.add(
            responses.POST,
            (
                u'https://api.github.com/repos/CanonicalJS/juju-gui/issues/5/'
                u'comments'
            ),
            body=new_comment,
            status=201,
            content_type='application/json'
        )

        info = GithubInfo('juju', 'project', 'jujugui', None)
        pr_info = make_pull_request_info(pull_request)
        resp = pull_request_kicked(pr_info, 'http://jenkins/job/1', info)
        comment = resp['body']
        self.assertIn(github.MERGE_SCHEDULED, comment)

    @responses.activate
    def test_requeue_after_fail(self):
        comments = load_data('github-pull-request-comments-requeue.json')

        self.add_user_orgs_response("mitechie")
        self.add_open_pulls_response("CanonicalJS", "juju-gui")
        responses.add(
            responses.GET,
            (
                u'https://api.github.com/repos/CanonicalJS/juju-gui/issues/5/'
                u'comments'
            ),
            body=comments,
            status=200,
            content_type='application/json'
        )

        info = GithubInfo('CanonicalJS', 'juju-gui', 'jujugui', None)
        mergeable = mergeable_pull_requests('$$merge$$', info)

        self.assertEqual(1, len(mergeable))
        self.assertEqual(5, mergeable[0].number)

    @responses.activate
    def test_requeue_after_fail_pending(self):
        comments = load_data(
            'github-pull-request-comments-requeue.json',
            load_json=True)
        # Remove the last comment, which is the second $$merge$$ marker
        comments.pop()

        self.add_user_orgs_response("mitechie")
        self.add_open_pulls_response("CanonicalJS", "juju-gui")
        responses.add(
            responses.GET,
            (
                u'https://api.github.com/repos/CanonicalJS/juju-gui/issues/5/'
                u'comments'
            ),
            body=json.dumps(comments),
            status=200,
            content_type='application/json'
        )

        info = GithubInfo('CanonicalJS', 'juju-gui', 'jujugui', None)
        mergeable = mergeable_pull_requests('$$merge$$', info)

        # No merge proposals as $$merge$$ has not been signaled since failure
        self.assertEqual(0, len(mergeable))
