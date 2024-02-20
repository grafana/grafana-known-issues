import requests
import os
import json
import re
import sys
import json
from datetime import datetime

def print_issues_to_file(issues, subfile):
    with open(f'issues-{subfile}.json', 'w') as file:
        json.dump(issues, file, indent=4)

def fetch_github_issues(currentPage, pagesToGet, startswith):
    # GitHub GraphQL API endpoint
    github_api_url = 'https://api.github.com/graphql'

    # Your GitHub personal access token
    # Generate one from: https://github.com/settings/tokens

    token = os.environ.get('GH_TOKEN')

    # Your GitHub repository owner and name
    owner = 'grafana'
    repo_name = 'grafana'

    if startswith == None:
        # GraphQL query to fetch issues with label "type/bug"
        query = '''
        query {
            repository(owner: "%s", name: "%s") {
                issues(labels: ["type/bug"], first: 100, orderBy: {field: CREATED_AT, direction: DESC}) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        url
                        title
                        body
                        state
                    }
                }
            }
        }
        ''' % (owner, repo_name)
    else:
        query = '''
        query {
            repository(owner: "%s", name: "%s") {
                issues(labels: ["type/bug"], first: 100, orderBy: {field: CREATED_AT, direction: DESC}, after: "%s") {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        url
                        title
                        body
                        state
                    }
                }
            }
        }
        ''' % (owner, repo_name, startswith)

    # Set up headers with the GitHub token
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    # Make the GraphQL request
    try:
        response = requests.post(github_api_url, json={'query': query}, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return

    # Parse the response and extract relevant information
    data = response.json()
    try:
        issues = data['data']['repository']['issues']['nodes']
    except KeyError:
        print("Error: Invalid response from GitHub API")
        return []
    
    # pagination
    if currentPage < pagesToGet and data['data']['repository']['issues']['pageInfo']['hasNextPage']:
        # print rate limit info here
        print(f'Rate Limit: {response.headers["X-RateLimit-Remaining"]}/{response.headers["X-RateLimit-Limit"]}')
        print(f'Rate Limit Reset: {response.headers["X-RateLimit-Reset"]}')
        print(f'Current Page: {currentPage}/{pagesToGet}')
        # go to next page
        issues += fetch_github_issues(currentPage + 1, pagesToGet, data['data']['repository']['issues']['pageInfo']['endCursor'])
    return issues


def find_grafana_version():
    # get issues from issues.json
    with open('issues-with_fixed.json', 'r') as file:
        issues = json.load(file)
    
    updated_issues = []
    
    for issue in issues:
        body = issue['body']
        lines = body.split('\n')
        found_in = None
        found_in_line = None
        
        for line in lines:
            version_match = re.search(r'\d+\.\d+\.\d+', line)
            if 'Grafana:' in line or 'Grafana Version:' in line or 'Grafana version:' in line:
                version_match = re.search(r'\d+\.\d+\.\d+', line)
                if version_match:
                    found_in = version_match.group()
                else:
                    found_in_line = line
                break  # no need to go through the rest of the lines
        
        if 'fixed_in' not in issue:
            issue['fixed_in'] = None
        updated_issue = {
            'url': issue['url'],
            'title': issue['title'],
            'body': issue['body'],
            'state': issue['state'],
            'found_in': found_in,
            'fixed_in': issue['fixed_in'], # added this to the dict to make it easier to find the issue in GitHub
            'found_in_line': found_in_line
        }
        
        updated_issues.append(updated_issue)
    
    with open('issues_with_found_in.json', 'w') as file:
        json.dump(updated_issues, file, indent=4)

def organize_issues_by_version():
    # get issues from issues.json
    with open('issues_with_found_in.json', 'r') as file:
        issues = json.load(file)
    
    issues_by_version = {}
    issues_with_found_in_line = []
    
    for issue in issues:
        version = issue['found_in']
        found_in_line = issue['found_in_line']
        if 'fixed_in' not in issue:
            issue['fixed_in'] = None
        
        if version:
            if version not in issues_by_version:
                issues_by_version[version] = []
            issues_by_version[version].append({
                'url': issue['url'],
                'title': issue['title'],
                'fixed_in': issue['fixed_in'], # added this to the dict to make it easier to find the issue in GitHub
                'state': issue['state'],
            })
        elif found_in_line:
            issues_with_found_in_line.append({
                'url': issue['url'],
                'title': issue['title'],
                'state': issue['state'],
                'fixed_in': issue['fixed_in'], # added this to the dict to make it easier to find the issue in GitHub
                'found_in_line': found_in_line
            })
        else:
            if 'No Version' not in issues_by_version:
                issues_by_version['No Version'] = []
            issues_by_version['No Version'].append({
                'url': issue['url'],
                'title': issue['title'],
                'fixed_in': issue['fixed_in'], # added this to the dict to make it easier to find the issue in GitHub
                'state': issue['state'],
            })

    # sort issues by title
    for version in issues_by_version:
        issues_by_version[version] = sorted(issues_by_version[version], key=lambda k: k['title'])
        
    with open('issues_by_version.json', 'w') as file:
        json.dump(issues_by_version, file, indent=4)

def log_stats():
    # get issues from issues.json
    with open('issues_by_version.json', 'r') as file:
        issues = json.load(file)
    
    sorted_versions = sorted(issues.keys())
    
    with open('stats.txt', 'w') as stats_file:
        for version in sorted_versions:
            stats_file.write(f'{version}: {len(issues[version])}\n')
    
        # total issues
        with open('issues.json', 'r') as file:
            issues = json.load(file)
        stats_file.write(f'- Total Bugs Scanned: {len(issues)}\n')

        # total open bugs
        with open('issues_with_found_in.json', 'r') as file:
            issues = json.load(file)
        open_issues = [issue for issue in issues if issue['state'] == 'OPEN']
        stats_file.write(f'- Total Open Bugs: {len(open_issues)}\n')
        
        # total closed bugs
        closed_issues = [issue for issue in issues if issue['state'] == 'CLOSED']
        stats_file.write(f'- Total Closed Bugs: {len(closed_issues)}\n')

        # total bugs with found_in
        with open('issues_with_found_in.json', 'r') as file:
            issues = json.load(file)
        issues_with_found_in = [issue for issue in issues if issue['found_in'] is not None]
        stats_file.write(f'- Total Bugs with Version: {len(issues_with_found_in)}\n')

        # total bugs with found_in_line
        with open('issues_with_found_in.json', 'r') as file:
            issues = json.load(file)
        issues_with_found_in_line = [issue for issue in issues if issue['found_in_line'] is not None]
        stats_file.write(f'- Total Bugs with Version (but not exact version): {len(issues_with_found_in_line)}\n')
    
    # print stats on screen
    with open('stats.txt', 'r') as file:
        stats = file.read()
        print(stats)

def create_report_md(showClosed=True, showOpen=True, filename='report.md'):
    # get issues from issues.json
    with open('issues_by_version.json', 'r') as file:
        issues = json.load(file)
    
    sorted_versions = sorted(issues.keys())
    
    with open(f'reports/{filename}', 'w', encoding='utf-8') as report_file:

        # print header
        report_file.write(f'# Grafana Bug Report\n')
        # print date
        current_date = datetime.now().strftime("%Y-%m-%d")
        report_file.write(f'## Date: {current_date}\n')
    
        for version in sorted_versions:            
            sorted_issues = sorted(issues[version], key=lambda x: x['state'], reverse=True)
            printed = 0
            for index, issue in enumerate(sorted_issues):

                if issue["state"] == 'OPEN' and showOpen == False:
                    continue
                elif issue["state"] == 'CLOSED' and showClosed == False:
                    continue

                # if issue['fixed_in'] == None:
                #     issue['fixed_in'] = ''
                if printed == 0:
                    report_file.write(f'## {version}\n')
                if index == 0 or issue['state'] != sorted_issues[index-1]['state']:
                    if showClosed == True and showOpen == True:
                        report_file.write(f'### {issue["state"]}\n')
                if issue['fixed_in'] != None:
                    report_file.write(f'- [{issue["title"]}]({issue["url"]}) (Fixed in {issue["fixed_in"]})\n')
                else:
                    report_file.write(f'- [{issue["title"]}]({issue["url"]})\n')
                printed += 1
                
            

        # total issues
        report_file.write(f'## Stats\n')
        with open('issues.json', 'r') as file:
            issues_data = json.load(file)
        report_file.write(f'- Total Bugs Scanned: {len(issues_data)}\n')

        # total open bugs
        with open('issues_with_found_in.json', 'r') as file:
            issues = json.load(file)
        open_issues = [issue for issue in issues if issue['state'] == 'OPEN']
        report_file.write(f'- Total Open Bugs: {len(open_issues)}\n')
        
        # total closed bugs
        closed_issues = [issue for issue in issues if issue['state'] == 'CLOSED']
        report_file.write(f'- Total Closed Bugs: {len(closed_issues)}\n')

        # total bugs with found_in
        with open('issues_with_found_in.json', 'r') as file:
            issues = json.load(file)
        issues_with_found_in = [issue for issue in issues if issue['found_in'] is not None]
        report_file.write(f'- Total Bugs with Version: {len(issues_with_found_in)}\n')

        # Total bugs with found_in and OPEN state
        open_issues_with_found_in = [issue for issue in issues_with_found_in if issue['state'] == 'OPEN']
        report_file.write(f'- Total Bugs with Version and OPEN state: {len(open_issues_with_found_in)}\n')


        # total bugs with found_in_line
        with open('issues_with_found_in.json', 'r') as file:
            issues = json.load(file)
        issues_with_found_in_line = [issue for issue in issues if issue['found_in_line'] is not None]
        report_file.write(f'- Total Bugs with Version (but not exact version): {len(issues_with_found_in_line)}\n')

def update_issues_json_with_new_issues(issues):
    # get issues from issues.json
    with open('issues.json', 'r') as file:
        old_issues = json.load(file)
    
    # merge old and new issues
    merged_issues = issues + old_issues

    # remove duplicates
    merged_issues = [dict(t) for t in {tuple(d.items()) for d in merged_issues}]
    
    # write to issues.json
    with open('issues.json', 'w') as file:
        json.dump(merged_issues, file, indent=4)
def get_linked_issue(issue_url):
    # get ID from issue URL
    issue_id = issue_url.split('/')[-1]
    # GitHub GraphQL API endpoint
    github_api_url = 'https://api.github.com/graphql'

    # Your GitHub personal access token
    token = os.environ.get('GH_TOKEN')

    # get the timeline items of the issue
    query = '''
 query {
        repository(owner: "grafana", name: "grafana") {
            issue(number: %s) {
              id
              timelineItems(first: 100, itemTypes: [CONNECTED_EVENT]) {
                                nodes {
                                    ... on ConnectedEvent {
                                        subject {
                                            ... on Issue {
                                                url
                                            }
                                            ... on PullRequest {
                                                url
                                            }
                                        }
                                    }
                                }
                            }
            }
                    
                }
            }
    ''' % (issue_id)

    # Set up headers with the GitHub token
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    # Make the GraphQL request
    try:
        response = requests.post(github_api_url, json={'query': query}, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return
    print(f'Rate Limit: {response.headers["X-RateLimit-Remaining"]}/{response.headers["X-RateLimit-Limit"]}')
    if response.json()['data']['repository']['issue']['timelineItems']['nodes']:
        return response.json()['data']['repository']['issue']['timelineItems']['nodes'][0]['subject']['url']
    else:
        return None

def get_milestone(issue_url):
    # get ID from issue URL
    issue_id = issue_url.split('/')[-1]
    # GitHub GraphQL API endpoint
    github_api_url = 'https://api.github.com/graphql'

    # Your GitHub personal access token
    token = os.environ.get('GH_TOKEN')

    if 'pull' in issue_url:
        # get the timeline items of the issue
        query = '''
        query {
            repository(owner: "grafana", name: "grafana") {
                pullRequest(number: %s) {
                    milestone {
                        title
                    }
                }
            }
        }
        ''' % (issue_id)
    else:

    # get the timeline items of the issue
        query = '''
        query {
            repository(owner: "grafana", name: "grafana") {
                issue(number: %s) {
                    milestone {
                        title
                    }
                }
            }
        }
        ''' % (issue_id)

    # Set up headers with the GitHub token
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    # Make the GraphQL request
    try:
        response = requests.post(github_api_url, json={'query': query}, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return
    
    if response.json()['data']['repository']:
        # check for issue or pull request key
        
        if 'issue' in response.json()['data']['repository']:
            if response.json()['data']['repository']['issue']['milestone'] != None and 'title' in response.json()['data']['repository']['issue']['milestone']:
                return response.json()['data']['repository']['issue']['milestone']['title']
        else:
            if response.json()['data']['repository']['pullRequest']['milestone'] != None and 'title' in response.json()['data']['repository']['pullRequest']['milestone']:
                return response.json()['data']['repository']['pullRequest']['milestone']['title']
            
            return None
def find_fixed_in_version():
    # gets all issues from issues.json
    with open('issues.json', 'r') as file:
        issues = json.load(file)

        # for each closed issues, find linked issue and get milestone
        for issue in issues:
            if issue['state'] == 'CLOSED':
                # get linked issue
                linked_issue = get_linked_issue(issue['url'])
                if linked_issue:
                    # get milestone
                    if linked_issue != None:
                        milestone = get_milestone(linked_issue)
                        if milestone:
                            # add milestone to issue
                            issue['fixed_in'] = milestone
                        else:
                            issue['fixed_in'] = None
                    else:
                            issue['fixed_in'] = None
                else:
                        issue['fixed_in'] = None
            else:
                issue['fixed_in'] = None
    return issues


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--no-cache':
        issues = fetch_github_issues(0, 20, None)
        update_issues_json_with_new_issues(issues)
        print_issues_to_file(find_fixed_in_version(), 'with_fixed')
    find_grafana_version()
    organize_issues_by_version()
    log_stats()
    create_report_md(False, True, "open_report.md")
    create_report_md(True, False, "closed_report.md")
    create_report_md(True, True, "all_report.md")
