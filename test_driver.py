import json,time,urllib.request as U,urllib.error as X
def c(m,p,b=None,t=None):
    r=U.Request("http://127.0.0.1:8000"+p,json.dumps(b or {}).encode() if m!="GET" else None,method=m,headers={"Authorization":"Bearer "+str(t),"Content-Type":"application/json"})
    try: x=U.urlopen(r);d=x.read();return x.status,(d if p=="/driver" else json.loads(d))
    except X.HTTPError as e:return e.code,json.loads(e.read())
s,h=c("GET","/driver");assert s==200 and "السائق".encode() in h
L=lambda p,pw:c("POST","/api/login",{"phone":p,"password":pw})[1].get("token")
A=L("0910000000","AdminPass123");c("PUT","/api/admin/settings",{"driver_limit":8},A)
did=c("POST","/api/admin/drivers",dict(name="سائق",phone="0921111111",password="DriverPass1",car="Kia",model="Rio",year=2020,color="أبيض",plate="111"),A)[1]["id"]
assert c("POST","/api/login",{"phone":"0921111111","password":"bad"})[0]==401
D=L("0921111111","DriverPass1");c("POST","/api/register",dict(name="عميل",phone="0931111111",password="CustPass123"));C=L("0931111111","CustPass123")
me=lambda:c("GET","/api/me",t=D)[1]["driver"];offers=lambda:c("GET","/api/driver/offers",t=D)[1]
mk=lambda u=False:c("POST","/api/orders",dict(service_id=1,pickup="أ",dropoff="ب",details="x",urgent=u),C)[1]["id"]
assert me()["available"]==0 and me()["outstanding"]==0
o1=mk();assert offers()==[],"unavailable gets nothing"
c("POST","/api/driver/available",{"available":True},D);of=offers();assert of[0]["order_id"]==o1 and "pickup" in of[0]
assert c("POST",f"/api/driver/offers/{o1}/reject",t=D)[0]==200 and offers()==[]
c("POST",f"/api/orders/{o1}/cancel",t=C)
def finish(o,price):
    assert not any("customer" in k for z in offers() for k in z),"no contact before accept"
    assert c("POST",f"/api/driver/offers/{o}/accept",{"agreed_price":price},D)[0]==200
    ro=[z for z in c("GET","/api/driver/orders",t=D)[1] if z["id"]==o][0];assert ro["customer_name"]=="عميل" and ro["customer_phone"]=="0931111111"
    assert c("POST",f"/api/driver/orders/{o}/status",{"status":"DELIVERED"},D)[0]==409
    for s_ in["DRIVER_ON_THE_WAY","DRIVER_ARRIVED","ORDER_PICKED_UP"]:assert c("POST",f"/api/driver/orders/{o}/status",{"status":s_},D)[0]==200
    assert c("POST",f"/api/driver/orders/{o}/cancel",t=D)[0]==409
    for s_ in["ON_THE_WAY_TO_CUSTOMER","DELIVERED"]:assert c("POST",f"/api/driver/orders/{o}/status",{"status":s_},D)[0]==200
    ro=[z for z in c("GET","/api/driver/orders",t=D)[1] if z["id"]==o][0];assert ro["customer_phone"] is None and ro["customer_name"] is None
o2=mk(True);finish(o2,40);assert me()["outstanding"]==6
o3=mk();assert c("POST",f"/api/driver/offers/{o3}/accept",{},D)[0]==200
c("POST",f"/api/driver/orders/{o3}/status",{"status":"DRIVER_ON_THE_WAY"},D)
assert c("POST",f"/api/driver/orders/{o3}/cancel",t=D)[0]==200 and c("GET",f"/api/orders/{o3}",t=C)[1]["status"]=="SEARCHING_DRIVER" and offers()==[]
c("POST",f"/api/orders/{o3}/cancel",t=C)
o4=mk();finish(o4,20);assert me()["outstanding"]==9
assert c("GET","/api/notifications",t=D)[1][0]["text"].startswith("وصلت عهدتك")
o5=mk();assert offers()==[],"blocked at limit"
assert c("POST","/api/driver/handover-request",t=D)[0]==200 and c("POST","/api/driver/handover-request",t=D)[0]==409
hid=c("GET","/api/admin/handovers",t=A)[1][0]["id"];assert c("POST",f"/api/admin/handovers/{hid}/confirm",t=D)[0]==403
assert c("POST",f"/api/admin/handovers/{hid}/confirm",t=A)[0]==200 and me()["outstanding"]==0
nt=[n["text"] for n in c("GET","/api/notifications",t=D)[1] if n["text"].startswith("وصلت عهدتك") or n["text"]=="تم تأكيد استلام العهدة"];assert nt[0]=="تم تأكيد استلام العهدة" and offers()[0]["order_id"]==o5
lg=c("GET","/api/driver/ledger",t=D)[1];assert [l["kind"] for l in lg]==["HANDOVER","COMMISSION","COMMISSION"] and len(c("GET","/api/driver/orders",t=D)[1])==2
c("POST",f"/api/driver/offers/{o5}/reject",t=D);c("PUT","/api/admin/settings",{"offer_timeout":1},A);o6=mk();assert offers()[0]["order_id"]==o6
time.sleep(2.2);assert offers()==[] and c("POST",f"/api/driver/offers/{o6}/accept",{},D)[0]==409
assert c("GET","/api/admin/stats",t=D)[0]==403 and c("PUT","/api/admin/settings",{"commission":0},D)[0]==403 and c("GET",f"/api/orders/{o2}",t=D)[0]==200
c("POST","/api/driver/available",{"available":False},D);assert me()["available"]==0
print("DRIVER OK")
