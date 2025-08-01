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
    
    sorted_versions = sorted(
        (version for version in issues.keys() if version != 'No Version'),
        key=parse_version_for_sorting,
        reverse=True
    )
    if 'No Version' in issues:
        sorted_versions.append('No Version')

    
    # group together all major/minor versions, basically remove the patch version and group together, e.g. 11.4.1 and 11.4.2 become 11.4 and we group the issues together.
    major_minor_versions = {}
    for version in sorted_versions:
        if version == 'No Version':
            major_minor_version = 'No Version'
        else:
            major_minor_version = '.'.join(version.split('.')[:2])
        
        if major_minor_version not in major_minor_versions:
            major_minor_versions[major_minor_version] = []
        
        major_minor_versions[major_minor_version] += issues[version]

    with open('reports/stats_by_major_minor_version.csv', 'w') as csv_file:
        csv_file.write(f'Version, Total, Open, Closed\n')
        for version in major_minor_versions:
            # group the issues by state
            open_issues = [issue for issue in major_minor_versions[version] if issue['state'] == 'OPEN']
            closed_issues = [issue for issue in major_minor_versions[version] if issue['state'] == 'CLOSED']
            csv_file.write(f'{version}, {len(major_minor_versions[version])}, {len(open_issues)}, {len(closed_issues)}\n')  
    
    with open('stats.txt', 'w') as stats_file:
        stats_file.write(f'Grafana Bug Report\n')
        current_date = datetime.now().strftime("%Y-%m-%d")
        stats_file.write(f'Date: {current_date}\n\n')

        stats_file.write(f'## By Version\n')
        with open('reports/stats_by_version.csv', 'w') as csv_file:
            csv_file.write(f'Version, Total, Open, Closed\n')
            stats_file.write(f'Version, Total, Open, Closed\n')
            for version in sorted_versions:
                # group the issues by state
                open_issues = [issue for issue in issues[version] if issue['state'] == 'OPEN']
                closed_issues = [issue for issue in issues[version] if issue['state'] == 'CLOSED']
                stats_file.write(f'{version}, {len(issues[version])}, {len(open_issues)}, {len(closed_issues)}\n')
                csv_file.write(f'{version}, {len(issues[version])}, {len(open_issues)}, {len(closed_issues)}\n')

    
        stats_file.write(f'\n\n## Overall Stats\n')
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
    
    sorted_versions = sorted(
        (version for version in issues.keys() if version != 'No Version'),
        key=parse_version_for_sorting,
        reverse=True
    )
    if 'No Version' in issues:
        sorted_versions.append('No Version')
    
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
        
        repository_data = response.json().get('data', {}).get('repository', {})
        if 'issue' in repository_data:
            milestone = repository_data.get('issue', {}).get('milestone', {})
            if milestone and 'title' in milestone:
                return milestone['title']
        elif 'pullRequest' in repository_data:
            pr = repository_data.get('pullRequest', {})
            if pr and 'milestone' in pr:
                milestone = pr.get('milestone', {})
                if milestone and 'title' in milestone:
                    return milestone['title']
            
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

def fetch_a_list_of_tags_from_github():

    # check if a tags file exists first, or if --no-cache is passed
    if os.path.exists('tags.json') and '--no-cache' not in sys.argv:
        with open('tags.json', 'r') as file:
            return json.load(file)

    # GitHub GraphQL API endpoint
    github_api_url = 'https://api.github.com/graphql'

    # Your GitHub personal access token
    token = os.environ.get('GH_TOKEN')

    # Your GitHub repository owner and name
    owner = 'grafana'
    repo_name = 'grafana'

    # GraphQL query to fetch issues with label "type/bug"
    query = '''
    query {
        repository(owner: "%s", name: "%s") {
            refs(refPrefix: "refs/tags/", first: 100, orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
                nodes {
                    name
                }
            }
        }
    }
    ''' % (owner, repo_name)

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
        tags = data['data']['repository']['refs']['nodes']
    except KeyError:
        print("Error: Invalid response from GitHub API")
        return []
    
    # remove any tag that doesn't match the pattern v\d+\.\d+\.\d+
    tags = [tag for tag in tags if re.match(r'v\d+\.\d+\.\d+', tag['name'])]

    # change this to just an array of names
    tags = [tag['name'] for tag in tags]

    # save the tags file to tags.json
    with open('tags.json', 'w') as file:
        json.dump(tags, file, indent=4)
    
    return tags

def parse_version_for_sorting(version_string):
    """
    Parse a version string (e.g., 'v11.4.2+security-01' or '11.4.2') and return a tuple for sorting.
    Handles special formats like +security, -preview, etc.
    """
    # Remove 'v' prefix if present
    version = version_string.lstrip('v')
    
    # Split by dots
    parts = version.split('.')
    
    if len(parts) < 3:
        # Handle incomplete versions by padding with zeros
        parts.extend(['0'] * (3 - len(parts)))
    
    major = int(parts[0])
    minor = int(parts[1])
    
    # Handle patch version with special characters
    patch_part = parts[2]
    # Extract numeric part before any special characters
    patch = int(patch_part.split('+')[0].split('-')[0])
    
    return (major, minor, patch)

def normalize_version_for_comparison(version_string):
    """
    Normalize a version string by removing 'v' prefix and any security/preview suffixes.
    Returns the base version (e.g., '11.4.2' from 'v11.4.2+security-01')
    """
    # Remove 'v' prefix
    version = version_string.lstrip('v')
    
    # Split by dots
    parts = version.split('.')
    
    if len(parts) < 3:
        # Handle incomplete versions by padding with zeros
        parts.extend(['0'] * (3 - len(parts)))
    
    # Extract numeric part before any special characters for patch
    patch_part = parts[2]
    patch = patch_part.split('+')[0].split('-')[0]
    
    return f"{parts[0]}.{parts[1]}.{patch}"

def get_prior_release(release_version, known_release_versions):
    """
    Get the prior release version, handling security patches and special versions.
    Returns the prior release version or None if not found.
    """
    # Normalize the current release version
    current_normalized = normalize_version_for_comparison(release_version)
    
    # Parse the normalized version
    version_parts = current_normalized.split('.')
    major = int(version_parts[0])
    minor = int(version_parts[1])
    patch = int(version_parts[2])
    
    # Calculate the expected prior release
    if patch > 0:
        # Same major.minor, previous patch
        expected_prior = f"{major}.{minor}.{patch-1}"
    else:
        if minor > 0:
            # Previous minor version, find the highest patch
            expected_prior = f"{major}.{minor-1}."
        else:
            # Previous major version, find the highest minor.patch
            expected_prior = f"{major-1}."
    
    # Find the best matching prior release
    best_match = None
    best_match_normalized = None
    
    for version in known_release_versions:
        if version == release_version:
            continue  # Skip the current version
            
        normalized = normalize_version_for_comparison(version)
        
        # Check if this version could be a prior release
        if patch > 0:
            # Looking for same major.minor, previous patch
            if normalized == expected_prior:
                best_match = version
                break
        else:
            # Looking for previous major.minor version
            if normalized.startswith(expected_prior):
                if best_match is None or parse_version_for_sorting(version) > parse_version_for_sorting(best_match):
                    best_match = version
                    best_match_normalized = normalized
    
    return best_match
    
def get_number_of_commits_between_two_releases(release_version, prior_release_version):
    """
    Get the number of commits between two releases using GitHub REST API.
    Returns the number of commits between prior_release_version and release_version.
    """
    if not prior_release_version:
        return 0
    
    # GitHub REST API endpoint for comparing commits
    github_api_url = f'https://api.github.com/repos/grafana/grafana/compare/{prior_release_version}...{release_version}'
    
    # Your GitHub personal access token
    token = os.environ.get('GH_TOKEN')
    
    if not token:
        print("Warning: GH_TOKEN not set, returning 0 for commit count")
        return 0
    
    # Set up headers with the GitHub token
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github.v3+json',
    }
    
    # Make the REST API request
    try:
        response = requests.get(github_api_url, headers=headers)
        response.raise_for_status()
        
        # Print rate limit info
        print(f'Rate Limit: {response.headers["X-RateLimit-Remaining"]}/{response.headers["X-RateLimit-Limit"]}')
        
        data = response.json()
        
        # The REST API returns 'ahead_by' field with the number of commits
        if 'ahead_by' in data:
            return data['ahead_by']
        else:
            print(f"Warning: Could not get comparison data for {prior_release_version}..{release_version}")
            return 0
            
    except requests.exceptions.RequestException as e:
        print(f"Error getting commit count between {prior_release_version} and {release_version}: {e}")
        return 0
    except KeyError as e:
        print(f"Error parsing response for {prior_release_version}..{release_version}: {e}")
        return 0

def review_release_info():
    releases = fetch_a_list_of_tags_from_github()

    # sort releases by major.minor.patch using robust parsing
    releases = sorted(releases, key=parse_version_for_sorting, reverse=True)

    with open('reports/release_stats.csv', 'w') as csv_file:
        csv_file.write(f'Version, Total, Open, Closed, Commits\n')
        for release in releases:
            # get the prior version
            prior_release = get_prior_release(release, releases)
            if prior_release == None:
                print(f'No prior release found for {release}')
                commits = 0
            else:
                # fetch how many commits between the two releases
                print(f'Getting commits between {release} and {prior_release}')
                commits = get_number_of_commits_between_two_releases(release, prior_release)
            # get issues from issues.json
            with open('issues_by_version.json', 'r') as file:
                issues = json.load(file)
                # find this release by looking through the keys for the version
                releaseWithoutV = release.lstrip('v')
                if releaseWithoutV in issues:
                    # group the issues by state
                    open_issues = [issue for issue in issues[releaseWithoutV] if issue['state'] == 'OPEN']
                    closed_issues = [issue for issue in issues[releaseWithoutV] if issue['state'] == 'CLOSED']
                    csv_file.write(f'{releaseWithoutV}, {len(issues[releaseWithoutV])}, {len(open_issues)}, {len(closed_issues)}, {commits}\n')
                else:   
                    csv_file.write(f'{releaseWithoutV}, 0, 0, 0, {commits}\n')

    # lets have a v2 that just groups together all the major.minor versions
    major_minor_versions = {}
    for release in releases:
        major_minor_version = release.lstrip('v').rsplit('.', 1)[0]
        if major_minor_version not in major_minor_versions:
            major_minor_versions[major_minor_version] = []
        major_minor_versions[major_minor_version].append(release)
    
    with open('reports/major_minor_release_stats.csv', 'w') as csv_file:
        csv_file.write(f'Version, Total, Open, Closed, Commits\n')
        with open('reports/release_stats.csv', 'r') as detailed_csv:
            detailed_csv.readline()
            for line in detailed_csv:
                version, total, open_issues, closed, commits = line.strip().split(',')
                major_minor_version = version.rsplit('.', 1)[0]
                if major_minor_version not in major_minor_versions:
                    major_minor_versions[major_minor_version] = []
                major_minor_versions[major_minor_version].append({
                    'version': version,
                    'total': int(total),
                    'open': int(open_issues),
                    'closed': int(closed),
                    'commits': int(commits)
                })
        
        for major_minor_version in major_minor_versions:
            total = sum([release['total'] for release in major_minor_versions[major_minor_version] if isinstance(release, dict)])
            open_issues_count = sum([release['open'] for release in major_minor_versions[major_minor_version] if isinstance(release, dict)])
            closed = sum([release['closed'] for release in major_minor_versions[major_minor_version] if isinstance(release, dict)])
            commits = sum([release['commits'] for release in major_minor_versions[major_minor_version] if isinstance(release, dict)])
            csv_file.write(f'{major_minor_version}, {total}, {open_issues_count}, {closed}, {commits}\n')
        

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

    review_release_info()
    
