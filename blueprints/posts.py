from flask import Blueprint,abort,flash,redirect,render_template,request,url_for
from db import get_db
from app import login_required,current_user


bp=Blueprint("posts",__name__)
def valid(v,a,b): return bool(v and a<=len(v.strip())<=b)

def category(db,v):
    if not v:return None
    try:i=int(v)
    except (ValueError,TypeError):return "bad"
    return i if db.execute("SELECT 1 FROM categories WHERE id=?",(i,)).fetchone() else "bad"

def tags(db,pid,raw):
    db.execute("DELETE FROM post_tags WHERE post_id=?",(pid,))
    seen=[]
    for x in (raw or "").split(","):
        x=" ".join(x.strip().split())
        if x and len(x)<=30 and x.lower() not in [z.lower() for z in seen]:seen.append(x)
    for x in seen[:10]:
        r=db.execute("SELECT id FROM tags WHERE lower(name)=lower(?)",(x,)).fetchone()
        if not r: db.execute("INSERT INTO tags(name) VALUES(?)",(x,)); r=db.execute("SELECT id FROM tags WHERE lower(name)=lower(?)",(x,)).fetchone()
        db.execute("INSERT OR IGNORE INTO post_tags VALUES(?,?)",(pid,r["id"]))

@bp.get("/")
def index():
    db=get_db(); q=request.args.get("q","").strip(); tag=request.args.get("tag","").strip(); cat=request.args.get("category","").strip()
    try: page=max(1,int(request.args.get("page","1")))
    except ValueError: page=1
    w=[]; p=[]
    if q:w.append("(p.title LIKE ? OR p.body LIKE ?)");p += [f"%{q}%",f"%{q}%"]
    if cat:
        try:w.append("p.category_id=?");p.append(int(cat))
        except ValueError:cat=""
    if tag:w.append("EXISTS(SELECT 1 FROM post_tags x JOIN tags y ON y.id=x.tag_id WHERE x.post_id=p.id AND lower(y.name)=lower(?))");p.append(tag)
    ws="WHERE "+" AND ".join(w) if w else ""; total=db.execute(f"SELECT COUNT(*) FROM posts p {ws}",p).fetchone()[0]; pages=max(1,(total+5)//6); page=min(page,pages)
    rows=db.execute(f"""SELECT p.*,u.username,c.name category_name,
                    (SELECT COUNT(*) FROM likes WHERE post_id=p.id) like_count,
                    (SELECT COUNT(*) FROM comments WHERE post_id=p.id) comment_count FROM posts p JOIN users u ON u.id=p.user_id LEFT JOIN categories c ON c.id=p.category_id {ws} ORDER BY p.created_at DESC LIMIT 6 OFFSET ?""",
                    p+[(page-1)*6]).fetchall()
    return render_template("index.html",posts=rows,q=q,tag=tag,category=cat,page=page,pages=pages,
                           tags=db.execute("SELECT * FROM tags ORDER BY name").fetchall(),categories=db.execute("SELECT * FROM categories ORDER BY name").fetchall())

@bp.get("/author/<int:uid>")
def author(uid):
    db=get_db(); u=db.execute("SELECT id,username FROM users WHERE id=?",(uid,)).fetchone()
    if not u:abort(404)
    ps=db.execute("SELECT p.*,(SELECT COUNT(*) FROM likes WHERE post_id=p.id) like_count,"
                  "(SELECT COUNT(*) FROM comments WHERE post_id=p.id) comment_count FROM posts p WHERE user_id=? ORDER BY created_at DESC",(uid,)).fetchall()
    return render_template("author.html",author=u,posts=ps)

@bp.get("/post/<int:pid>")
def post(pid):
    db=get_db(); p=db.execute("SELECT p.*,u.username,u.id author_id,"
                              "c.name category_name FROM posts p JOIN users u ON u.id=p.user_id LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=?",
                              (pid,)).fetchone()
    if not p:abort(404)
    cs=db.execute("SELECT c.*,u.username FROM comments c JOIN users u ON u.id=c.user_id WHERE c.post_id=? ORDER BY c.created_at",(pid,)).fetchall()
    ts=db.execute("SELECT t.* FROM tags t JOIN post_tags pt ON pt.tag_id=t.id WHERE pt.post_id=?",(pid,)).fetchall()
    likes=db.execute("SELECT COUNT(*) FROM likes WHERE post_id=?",(pid,)).fetchone()[0]; liked=False
    u=current_user()
    if u:liked=bool(db.execute("SELECT 1 FROM likes WHERE post_id=? AND user_id=?",(pid,u["id"])).fetchone())
    return render_template("post.html",post=p,comments=cs,tags=ts,likes=likes,liked=liked)

@bp.route("/post/new",methods=["GET","POST"])
@login_required
def new():
    db=get_db(); f=request.form if request.method=="POST" else {}; cats=db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    if request.method=="POST":
        t=f.get("title","").strip(); b=f.get("body","").strip(); c=category(db,f.get("category_id"))
        if not valid(t,3,160):flash("Заголовок: 3–160 символов.","error")
        elif not valid(b,1,20000):flash("Текст: 1–20 000 символов.","error")
        elif c=="bad":flash("Выбрана несуществующая категория.","error")
        else:
            cur=db.execute("INSERT INTO posts(user_id,category_id,title,body) VALUES(?,?,?,?)",(current_user()["id"],c,t,b)); 
            tags(db,cur.lastrowid,f.get("tags"));db.commit(); return redirect(url_for("posts.post",pid=cur.lastrowid))
    return render_template("post_form.html",post=None,categories=cats,form=f)

@bp.route("/post/<int:pid>/edit",methods=["GET","POST"])
@login_required
def edit(pid):
    db=get_db(); p=db.execute("SELECT * FROM posts WHERE id=?",(pid,)).fetchone()
    if not p:abort(404)
    u=current_user()
    if p["user_id"]!=u["id"] and u["role"]!="admin":abort(403)
    old=", ".join(x["name"] for x in db.execute("SELECT t.name FROM tags t JOIN post_tags pt ON pt.tag_id=t.id WHERE pt.post_id=?",(pid,)).fetchall())
    f=request.form if request.method=="POST" else {"title":p["title"],"body":p["body"],"category_id":p["category_id"] or "",
                                                   "tags":old};cats=db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    if request.method=="POST":
        t=f.get("title","").strip();b=f.get("body","").strip();c=category(db,f.get("category_id"))
        if not valid(t,3,160):flash("Заголовок: 3–160 символов.","error")
        elif not valid(b,1,20000):flash("Текст: 1–20 000 символов.","error")
        elif c=="bad":flash("Выбрана несуществующая категория.","error")
        else:db.execute("UPDATE posts SET title=?,body=?,category_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (t,b,c,pid)); tags(db,pid,f.get("tags"));db.commit(); return redirect(url_for("posts.post",pid=pid))
    return render_template("post_form.html",post=p,categories=cats,form=f)

@bp.post("/post/<int:pid>/delete")
@login_required
def delete(pid):
    db=get_db();p=db.execute("SELECT * FROM posts WHERE id=?",(pid,)).fetchone()
    if not p:abort(404)
    u=current_user()
    if p["user_id"]!=u["id"] and u["role"]!="admin":abort(403)
    db.execute("DELETE FROM posts WHERE id=?",(pid,));db.commit();return redirect(url_for("posts.index"))

@bp.post("/post/<int:pid>/comment")
@login_required
def comment(pid):
    db=get_db()
    if not db.execute("SELECT 1 FROM posts WHERE id=?",(pid,)).fetchone():abort(404)
    b=request.form.get("body","").strip()
    if not valid(b,1,3000):flash("Комментарий: 1–3000 символов.","error")
    else:db.execute("INSERT INTO comments(post_id,user_id,body) VALUES(?,?,?)",(pid,current_user()["id"],b));db.commit()
    return redirect(url_for("posts.post",pid=pid))

@bp.post("/comment/<int:cid>/delete")
@login_required
def del_comment(cid):
    db=get_db();c=db.execute("SELECT * FROM comments WHERE id=?",(cid,)).fetchone()
    if not c:abort(404)
    u=current_user()
    if c["user_id"]!=u["id"] and u["role"]!="admin":abort(403)
    db.execute("DELETE FROM comments WHERE id=?",(cid,));db.commit();return redirect(url_for("posts.post",pid=c["post_id"]))

@bp.post("/post/<int:pid>/like")
@login_required
def like(pid):
    db=get_db()
    if not db.execute("SELECT 1 FROM posts WHERE id=?",(pid,)).fetchone():abort(404)
    uid=current_user()["id"]; x=db.execute("SELECT 1 FROM likes WHERE post_id=? AND user_id=?",(pid,uid)).fetchone()
    if x:db.execute("DELETE FROM likes WHERE post_id=? AND user_id=?",(pid,uid))
    else:db.execute("INSERT INTO likes VALUES(?,?)",(pid,uid))
    db.commit();return redirect(request.referrer or url_for("posts.post",pid=pid))