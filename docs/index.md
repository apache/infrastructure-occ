# infrastructure-occ
On-Commit Commands

Simple daemon that runs commands when a commit to a certain source has happened.

Sample `occ.yaml` config:

~~~yaml
pubsub:
  url: https://pubsub.apache.org:2070/commit
  user: user
  pass: pass

subscriptions:
  git-change:
    topics: git/commit/some-git-repo-name
    oncommit: /x1/git/run-git-trigger.sh
    blamelist: notify@example.org
    blamesubject: Git trigger failure
  svn-change-in-dir:
    topics: svn/commit/somedir
    changedir: some/subdir
    oncommit: /x1/git/run-svn-trigger.sh
    blamelist: notify@example.org
    blamesubject: Subversion trigger failure

~~~

