#!python3
# Mehmet Hatip
try:
    import os, praw, imgurpython, logging, configparser, sys, requests, regex
    import subprocess, threading, time, queue, csv
except Exception as e:
    print(f'Error: {e}')
    sys.exit()

def clients(name, config=None):
    try:
        if not config:
            filename = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '.gitignore', 'client_info.ini')
            )
            config = configparser.ConfigParser()
            config.read(filename)
        if name == 'reddit':
            reddit = praw.Reddit(
            client_id = config['reddit']['client_id'],
            client_secret = config['reddit']['client_secret'],
            user_agent = config['reddit']['user_agent']
            )
            return reddit
        elif name == 'imgur':
            imgur = imgurpython.ImgurClient(
            client_id = config['imgur']['client_id'],
            client_secret = config['imgur']['client_secret']
            )
            return imgur
    except Exception as e:
        print(f'Error: {e}')
        sys.exit()

def find_extension(url):
    try:
        ext = regex.search(r'(\.\w{3,5})(\?.{1,2})?$', url).group(1)
        return ext
    except:
        return None

def clean(text):
    return regex.sub(r"[^\s\w',]", '', text).strip()

def slim_title(title, limit=250):
    name = clean(title)
    char_max = limit - len(os.path.abspath('.'))
    name = name[:char_max-1] if len(name) >= char_max else name
    return name

def streamable_url(url):
    try:
        id = regex.search(r'(\w+)([-\w]+)?$', url).group(1)
        req = requests.get('https://api.streamable.com/videos/' + id)
        url = 'http:' + req.json()['files']['mp4']['url']
    except:
        pass
    return url

def gfycat_url(url):
    try:
        id = regex.search(r'(\w+)([-\w]+)?$', url).group(1)
        req = requests.get('https://api.gfycat.com/v1/gfycats/' + id)
        url = req.json()['gfyItem']['mp4Url']
    except:
        pass
    return url

def subreddit_param(sub, section, time_filter, posts):
    if section == 'top':
        return sub.top(limit=posts, time_filter=time_filter)
    elif section == 'hot':
        return sub.hot(limit=posts)
    elif section == 'new':
        return sub.new(limit=posts)
    elif section == 'cont':
        return sub.controversial(limit=posts, time_filter=time_filter)

def make_dir(dir_name):
    if not os.path.isdir(dir_name):
        os.mkdir(dir_name)
    os.chdir(dir_name)

def get_size(start_path=os.getcwd()):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                try:
                    total_size += os.path.getsize(fp)
                except:
                    None
    gigs = total_size / 2 ** 30
    logging.info(f'{gigs} gigabytes in {os.path.abspath(start_path)}')
    return gigs

def download_subreddit(sub_name, section, time_filter, posts, storage, thread_num=3):
    if get_size(start_path='.') >= storage:
        logging.info(f'Exceeded {storage} gigabytes, exiting')
        return
    starttime = time.time()
    reddit = clients('reddit')
    try:
        if sub_name == 'r':
            sub = reddit.random_subreddit()
        else:
            sub = reddit.subreddit(sub_name)
        sub_name = clean(sub.display_name)
        title = clean(sub.title)
        if sub.over18:
            raise Exception('Nice try...')
    except Exception as e:
        print(f'Error: {e}\nDoes the subreddit exist?')
        return

    logging.info(f'\nSubreddit {sub_name} downloaded\n')
    make_dir(sub_name)

    logging.info('Start submission download')
    all_subs = []
    print(
    f"Downloading {sub_name}...",
    f"Title: {title}", sep='\n')

    for submission in subreddit_param(sub, section, time_filter, posts):
        all_subs.append(submission)

    logging.info('End submission download')
    threads = []
    thread_posts = [0] * thread_num
    sub_count = len(all_subs)
    remainder = sub_count % thread_num
    portion = int(sub_count / thread_num)

    logging.info(f'{section}, {time_filter}, {posts}')
    gigs_q = queue.LifoQueue(maxsize=100)
    posts_q = queue.LifoQueue(maxsize=100)
    my_lock = threading.Lock()

    for i in range(thread_num):
        start, end = i * portion, (i+1) * portion
        if i == thread_num - 1:
            end += remainder
        subs = all_subs[start:end]
        logging.info(f'Thread {i+1} gets [{start}:{end}]')
        threadObj = threading.Thread(
        target=download_subs,
        args=[subs, storage, i, posts_q, gigs_q, my_lock]
        )
        threads.append(threadObj)
        threadObj.start()

    total_posts = 0
    while threading.active_count() != 1:
        id, i = posts_q.get()
        thread_posts[id] = i
        total_posts = sum(thread_posts)
        gigs = gigs_q.get()
        percent = round(100 * max(total_posts / posts, gigs / storage))
        sys.stdout.write(f"\r{percent}%")

    for thread in threads:
        thread.join()
    os.chdir('..')
    sys.stdout.write(f"\r100%\n")
    endtime = time.time()
    duration = round(endtime-starttime, 1)
    print(f'{round(gigs, 2)}/{round(storage, 2)} gigabytes reached')
    print(f'{total_posts}/{posts} posts downloaded')
    print(f'Took {duration} seconds total')
    return (thread_num, posts, duration)

def download_subs(subs, storage, ID, posts_q, gigs_q, lock):
    i = 0
    for submission in subs:
        if submission.over_18:
            continue
        url = submission.url
        title = slim_title(submission.title)
        text = clean(submission.selftext)
        extension = find_extension(url)
        title_url = title + '.url'
        if os.path.isfile(title_url):
            raise Exception('File already exists')

        # logging
        logging.info(
        f"\nSUBMISSION INFO THREAD {ID}\n\t" +
        f"Initial URL: {str(url)}\n\t" +
        f"ID: {submission.id}\n\t" +
        f"Title: {title}\n\t" +
        f"Current dir: {os.getcwd()}")

        if bool(regex.search(r'imgur', url)):
            reg = regex.search(r'(imgur.com\/)(\w+\/)?(\w+)(\.\w+)?(.*)?$', url)
            domain, album, id, extension, bs = reg.groups()
            logging.info(
            f'Domain: "{domain}" Album: "{album}" ' +
            f'ID: "{id}" ext: "{extension}" bs: "{bs}"')
            if album:
                title = slim_title(title, limit=200)
                lock.acquire()
                logging.info('Locked threads for imgur album')
                imgur_album(title, id)
                lock.release()
                logging.info('Released lock after imgur album')
            else:
                name, url = imgur_image(title=title, id=id)
                lock.acquire()
                status = download_file(name, url)
                lock.release()
                logging.info(status)
        else:
            if submission.is_reddit_media_domain:
                if submission.is_video:
                    url = submission.media['reddit_video']['fallback_url']
                    if submission.media['reddit_video']['is_gif']:
                        extension = '.mp4'
                    else:
                        url_audio = regex.sub(r'\/[^\/]+$',r'/audio', url)
                        lock.acquire()
                        status = download_video(title, url, url_audio)
                        lock.release()
                        logging.info(status)
                        continue
                else:
                    extension = '.jpg'
            elif bool(regex.search(r'streamable\.com\/\w+', url)):
                url = streamable_url(url)
                extension = '.mp4'
            elif bool(regex.search(r'gfycat\.com\/\w+', url)):
                url = gfycat_url(url)
                extension = '.mp4'
            elif text:
                extension = '.txt'
            if extension:
                name = title + extension
                lock.acquire()
                logging.info('Lock acquired to download file')
                status = download_file(name, url, text=text)
                logging.info(status)
                lock.release()
                logging.info('Lock released')
            else:
                url = 'https://www.reddit.com' + submission.permalink
                text = '[InternetShortcut]\nURL=%s' % url
                lock.acquire()
                status = download_file(title_url, url, text=text)
                logging.info(status)
                lock.release()
        gigs = get_size(start_path='.')
        i += 1
        try:
            posts_q.put((ID, i))
            gigs_q.put(gigs)
        except:
            pass
        if gigs >= storage:
            return

def imgur_album(title, id):
    imgur = clients('imgur')
    make_dir(title)
    images = imgur.get_album_images(id)
    logging.info(f'Downloading imgur album')
    for item in images:
        name, url = imgur_image(item=item)
        status = download_file(name, url)
        logging.info('Imgur ' + status)

    os.chdir('..')
    logging.info('Finished imgur album')

def imgur_image(title=None, id=None, item=None):
    imgur = clients('imgur')
    if not id and not item:
        logging.info('Imgur image could not be downloaded')
        return
    item = imgur.get_image(id) if id else item
    if item.animated:
        url = item.mp4
    else:
        url = item.link
    logging.info(f'Imgur link: {url}')
    extension = find_extension(url)
    if item.title:
        title = slim_title(item.title, limit=250)
    elif not title:
        i = 1
        for filename in os.listdir('.'):
            if os.path.splitext(filename)[0] == f'Untitled {i}':
                i += 1
            else:
                break
        title = f'Untitled {i}'
    name = title + extension
    return name, url

def download_file(name, url, text=None):
    try:
        if text:
            saveFile = open(name, 'w')
            saveFile.write(text)
        else:
            res = requests.get(url, stream=True)
            #res.raise_for_status()
            saveFile = open(name, 'wb')
            for chunk in res:
                saveFile.write(chunk)
        saveFile.close()
        return f'File successfully downloaded'
    except Exception as e:
        return (f'Error: {e}')

def download_video(name, video, audio):
    try:
        name_mp4 = slim_title(name) + '.mp4'
        if os.path.exists(name) or os.path.exists(name_mp4):
            raise Exception('File already exists')
        logging.info(f'Video name: {name_mp4}')
        status1 = download_file('video.mp4', video)
        status2 = download_file('audio.mp3', audio)
        logging.info(f'Video file: {status1}\nAudio file: {status2}')
        cmd = "ffmpeg -i %s -i %s -c:v copy -c:a aac -strict experimental %s"
        cmd = cmd % ('video.mp4', 'audio.mp3', 'combined.mp4')
        try:
            with open(os.devnull, 'w') as devnull:
                subprocess.run(cmd, stdout=devnull)
        except FileNotFoundError:
            dir = slim_title(name, limit=244)
            logging.info(f'Making \'{dir}\' and moving video/audio to it')
            os.mkdir(f'{dir}')
            os.rename('video.mp4', os.path.join(dir, 'video.mp4'))
            os.rename('audio.mp3', os.path.join(dir, 'audio.mp3'))
            return 'Could not combine video and audio, consider downloading ffmpeg'
        else:
            os.rename('combined.mp4', name_mp4)
            os.remove('video.mp4')
            os.remove('audio.mp3')
            return f'File successfully downloaded'
    except Exception as e:
        return f'Error: {e}'

def main():
    download_subreddit('r', 'top', 'all', 10, 1)

if __name__=='__main__':
    main()
