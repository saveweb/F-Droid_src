import asyncio
import logging
from pathlib import Path
import json
import argparse

import httpx

from fdroid_push_swh.swh import git_swh

json_url = 'https://f-droid.org/repo/index-v2.json'
json_cache = Path('index-v2.json')
success_repos = Path('success_repos.txt')


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true', help='Redownload index-v2.json')
    parser.add_argument('--swh-token', type=str)
    parser.add_argument('--list-only', action='store_true', help='Only list repos to sourceCodes.txt, do not submit to SWH')
    return parser.parse_args()

async def main():
    args = parse_args()
    if not args.refresh and json_cache.exists():
        with json_cache.open('rb') as f:
            data = json.load(f)
    else:
        print('Downloading index-v2.json...')
        r = httpx.get(json_url, follow_redirects=True)
        r.raise_for_status()
        with json_cache.open('wb') as f:
            f.write(r.content)
        data: dict = json.loads(r.content)
    print(len(data)//1024//1024, 'MiB')
    packages = data.get('packages', {})

    # now = time.time()

    new_packages = {}
    for package_name in packages:
        package = packages[package_name]
        # if package['metadata']['added']/1000 > now - 60*60*24*30:
        #     # print(package_name)
        new_packages.update({package_name: package})

    print('Sorting new packages...1')
    # newest first
    # package["metadata"]["added"]
    new_packages_names = list(new_packages)
    new_packages_added = [new_packages[package_name]['metadata']['added'] for package_name in new_packages_names]
    new_packages_added, new_packages_names = zip(*sorted(zip(new_packages_added, new_packages_names), reverse=True))
    print('Sorting new packages...2')
    sorted_new_packages = {}
    for package_name in new_packages_names:
        # print(new_packages[package_name]['metadata']['added'], package_name)
        sorted_new_packages.update({package_name: new_packages[package_name]})
    print(len(sorted_new_packages))


    sourceCodes = set()
    for package in sorted_new_packages.values():
        # rprint(package)
        added = package['metadata']['added']
        sourceCode = package['metadata'].get("sourceCode")
        if sourceCode: # some are None
            print(added, sourceCode)
            sourceCodes.add(sourceCode)
        # time.sleep(0.1)
    
    with open("sourceCodes.txt", "w") as f:
        f.write("\n".join(sourceCodes)+"\n")

    print("sourceCodes.txt written")

    if args.list_only:
        return

    success_repos_text = success_repos.read_text() if success_repos.exists() else ''
    

    cors_list = []
    cors_codes = []
    cors_workers = 10

    logging.info('Starting...')

    # very bad implementation, but it's just a simple script :)

    while sourceCode := sourceCodes.pop() if len(sourceCodes) > 0 else None:
        if sourceCode in success_repos_text:
            logging.info('Skipping %s', sourceCode)
            continue
        cors_codes.append(sourceCode)

        assert args.swh_token, 'Please provide --swh-token'

        cor = git_swh(sourceCode, swh_token=args.swh_token)
        logging.info('Starting %s', sourceCode)
        await asyncio.sleep(0.5)
        cors_list.append(cor)
        if len(cors_list) >= cors_workers or len(sourceCodes) == 0:
            await asyncio.gather(*cors_list)

            success_repos_text = success_repos.read_text() if success_repos.exists() else ''

            with success_repos.open('a') as f:
                for cors_code in cors_codes:
                    if cors_code not in success_repos_text:
                        f.write(cors_code + '\n')
            cors_list = []
            cors_codes = []

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())